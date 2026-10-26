"""The approvals staff endpoints (design §3.2-§3.4, §7; D-427, D-429): a project's switches, contract reference and
client party (``set_switches``), its approvers (``set_approver``, ``confirm_approver``), the site's evidence mailbox
(``set_evidence_mailbox``, ``confirm_evidence_mailbox``), sending a record for approval (``request``) and a priced
Decision's variation (``make_variation``); what the records do is approvals.subjects. P3-78: staff ``void`` and
``nudge`` an Open request, the client emails (the request, the supersede and void notes, a final record's change, the
reminders of the daily ``remind``) and the staff bell "Client answered" (``answered``).

- **Server-owned** (§3.2): ``guard`` (Construction Project and Approval Settings validate) compares each owned value,
  and each member row's approver values, with the saved copy and refuses a change unless this module saves that very
  document (``FLAG``), for every user, System Manager and Administrator included. A refusal throws and resets nothing. A
  member row may still be removed (membership has its own rules): someone who is no longer a member approves nothing,
  and the removal of an approver's row is a designation event too (``on_project_update``).
- **The chain decides** (§2 rule 5): each change is a chain event (``settings``, ``designation``, ``evidence_mailbox``),
  and ``approvers`` reads a project's approvers from its designation events, and only while the member's row still has
  ``may_approve``: a database edit of the column designates no one, and a removed and re-added contact's new row starts
  with none.
- **Mails** (§6): each approver change mails every client contact of the project the full approver list; Device location
  on mails the approvers; a mailbox change mails the old and the new address, the new one with its confirm link. A mail
  that cannot be queued is logged and never stops the change.
"""

import hmac
import json
import secrets
from urllib.parse import quote, urlencode

import frappe
from frappe import _
from frappe.utils import (add_days, add_to_date, cint, cstr, escape_html, flt, get_datetime, get_fullname, get_url,
	getdate, now_datetime, nowdate, validate_email_address)

from construction_core import client_files
from construction_core.approvals import canonical, frozen, log, read, subjects
from construction_core.files import versions
from construction_core.notifications import (APPROVAL_CHANGED, APPROVAL_OVERDUE, CLIENT_APPROVED, CLIENT_RETURNED, key,
	notify)
from construction_core.onboarding import invites
from construction_core.onboarding.mail import _brand_args, brand, credit_html
from construction_core.permissions import is_client, project_of
from construction_core.providers.storage import IMAGE_TYPES, clean_image

PROJECT, SETTINGS = "Construction Project", "Approval Settings"
FLAG = "cc_approvals_setup"
# A project's set-up, each field "cc_" + the key its settings event holds (§3.2 items 1, 2 and 5)
SET_UP = ("portal_approvals", "device_location", "contract_document", "contract_date", "contract_clause",
	"contract_file", "contract_file_name", "client_legal_name", "client_address")
OWNED = {PROJECT: tuple(f"cc_{key}" for key in SET_UP),
	SETTINGS: ("evidence_mailbox", "evidence_mailbox_confirmed", "evidence_token_hash", "evidence_token_expires")}
CHECKS = frozenset({"cc_portal_approvals", "cc_device_location", "evidence_mailbox_confirmed"})
TEXT_MAX = {"contract_document": 140, "contract_clause": 140, "client_legal_name": 140, "client_address": 500}
REQUIRED_ON = ("contract_document", "contract_date", "contract_clause", "client_legal_name", "client_address")
# §3.2 item 1: what the manager confirms by turning Portal approvals on, recorded word for word in the chain
CONFIRMATION = "Our contract with this client says approvals given in this portal are written approvals."
WAITING, CONFIRMED = "Waiting for confirmation", "Confirmed"
TOKEN_HOURS = 48
NOTE_MAX = 1000
# P3-78 (§3.4, §3.10, §3.13; M10): a staff void's short list of reasons (shown to the client), and the client emails
VOID_REASONS = ("Sent by mistake", "The record is being changed", "No longer needed", "Another reason")
NOTHING_NEEDED = "Nothing needed now. The team will send the updated version."
REQUEST_MAIL, NOTICE_MAIL = "templates/emails/cc_approval_request.html", "templates/emails/cc_approval_notice.html"


# --- server ownership -------------------------------------------------------------------------------------------


def guard(doc, method=None):
	"""validate of Construction Project and Approval Settings: the approval set-up changes only through this module."""
	if frappe.flags.get(FLAG) is doc:
		return
	before = doc.get_doc_before_save()  # None on insert: every value starts empty
	old = {r.user: _approver(r) for r in before.get("users") or []} if before is not None else {}
	if _owned(before if before is not None else frappe._dict(), doc.doctype) != _owned(doc, doc.doctype) \
			or any(_approver(r) != old.get(r.user, (0, "")) for r in doc.get("users") or []):
		frappe.throw(_("The approval set-up changes only through its own settings"), frappe.PermissionError)


def _owned(doc, doctype) -> list:
	return [cint(doc.get(f)) if f in CHECKS else cstr(doc.get(f)) for f in OWNED[doctype]]


def _approver(row) -> tuple:
	return cint(row.get("may_approve")), row.get("approver_state") or ""


def _save(doc):
	"""This module's own save of server-owned values: ``guard`` lets this very document through."""
	frappe.flags[FLAG] = doc
	try:
		doc.save(ignore_permissions=True)  # each endpoint checked its caller first
	finally:
		frappe.flags[FLAG] = None


def _project(project, ptype: str):
	doc = frappe.get_doc(PROJECT, project, for_update=True)  # the latest committed row, held to the end (log.lock)
	frappe.has_permission(PROJECT, ptype, doc=doc, throw=True)
	return doc


def _freeze_file(project, file, checked: bool = False) -> tuple[str, str]:
	"""A File of this project the caller reads, frozen (a contract or an authority document, §4.3): the frozen copy's
	SHA-256 and the file's name. ``checked``: a proof (a dispute's, §3.7; a recorded approval's, §3.9) first passes the
	client-file checks and the scan, an image re-encoded, as subjects.freeze does."""
	f = frappe.get_doc("File", file) if isinstance(file, str) and frappe.db.exists("File", file) else None
	if not f or f.is_folder or project_of(f) != project or not frappe.has_permission("File", "read", doc=f):
		raise frappe.DoesNotExistError(_("Not found"))
	content = frozen.original(f.name)
	if checked:
		ext = versions.split_name(f.file_name)[1].lstrip(".").lower()
		client_files.check_type(ext)
		client_files.check_signature(ext, content)
		client_files.check_structure(ext, content)
		client_files.scan(content, project=project)
		content = clean_image(content, ext) if ext in IMAGE_TYPES else content
	return frozen.store(content), cstr(f.file_name)[:140]


# --- the project's switches, contract reference and client party ------------------------------------------------


@frappe.whitelist(methods=["POST"])
def set_switches(project: str, portal_approvals: int | str | None = None, device_location: int | str | None = None,
		contract_document: str | None = None, contract_date: str | None = None, contract_clause: str | None = None,
		contract_file: str | None = None, client_legal_name: str | None = None, client_address: str | None = None) -> dict:
	"""A project's approval switches, contract reference and client party (§3.2 items 1, 2 and 5), by a Construction
	Manager of the project; a value not given stays. Portal approvals goes on only where the site allows it (site config
	``cc_approvals_enabled``, until P3-81's verify job) and with the contract reference and the client party; on, it
	records CONFIRMATION and opens the portal's approvals section to the clients; off, it voids every Open request.
	Device location on mails the approvers. contract_file: a File of this project, frozen; "" removes it."""
	given = {"portal_approvals": portal_approvals, "device_location": device_location,
		"contract_document": contract_document, "contract_date": contract_date, "contract_clause": contract_clause,
		"contract_file": contract_file, "client_legal_name": client_legal_name, "client_address": client_address}
	if "Construction Manager" not in frappe.get_roles():
		raise frappe.PermissionError(_("A Construction Manager sets up approvals"))
	return log.retry_once(lambda: _set_switches(project, {k: v for k, v in given.items() if v is not None}))


def _set_switches(project, given: dict) -> dict:
	doc = _project(project, "write")
	was = _settings(doc)
	for key in ("portal_approvals", "device_location"):
		if key in given:
			doc.set(f"cc_{key}", 1 if cint(given[key]) else 0)
	for key, limit in TEXT_MAX.items():
		if key in given:
			doc.set(f"cc_{key}", cstr(given[key]).strip()[:limit])
	if "contract_date" in given:
		doc.cc_contract_date = getdate(given["contract_date"]) if given["contract_date"] else None
	if "contract_file" in given:
		doc.cc_contract_file, doc.cc_contract_file_name = \
			_freeze_file(project, given["contract_file"]) if given["contract_file"] else ("", "")
	now = _settings(doc)
	on, switched = now["portal_approvals"] == "1", was["portal_approvals"] != now["portal_approvals"]
	if on and switched and not frappe.conf.get("cc_approvals_enabled"):
		frappe.throw(_("Portal approvals are not available on this site yet"), frappe.PermissionError)
	if on and not all(now[key] for key in REQUIRED_ON):
		frappe.throw(_("Enter the contract's name, date and clause and the client's legal name and address first"))
	voided = []
	if now != was:
		_save(doc)
		# the site's mailbox in force joins the project's chain here: the mailbox events reach only chains that exist
		mailbox = frappe.db.get_singles_dict(SETTINGS)
		log.append_event(doc.name, "settings", body={**now, "confirmation": CONFIRMATION if on else "",
			"evidence_mailbox": cstr(mailbox.get("evidence_mailbox")),
			"evidence_mailbox_confirmed": cstr(cint(mailbox.get("evidence_mailbox_confirmed")))})
		if on and switched:
			_approvals_section_on(doc.name)
		if switched and not on:
			for r in frappe.get_all(log.REQUEST, filters={"project": doc.name, "status": ["in", ("Open", log.INTERNAL)]},
					fields=subjects.FIELDS, order_by="name"):
				subjects.void(r, "Portal approvals turned off")  # a Waiting Decision then needs a new request
				voided.append(r.name)
		if now["device_location"] == "1" and was["device_location"] != "1":
			_mail([_email(u) for u in approvers(doc.name)], _("Device location is on for {0}").format(doc.project_name), [
				_("When you answer an approval request for {0}, you can now choose to share your device's location "
					"with your answer. It is only shared if you tick the box.").format(doc.project_name)])
	return {**now, "voided": voided}


def _settings(doc) -> dict:
	"""The project's set-up as its settings event holds it: text only ("0" or "1", a date as YYYY-MM-DD, "" for none)."""
	return {key: cstr(doc.get(f"cc_{key}")) for key in SET_UP}


def _approvals_section_on(project):
	"""Portal approvals on opens the portal's approvals section to the project's clients (permissions.DEFAULT_OFF), so
	its approvers can read its requests (§3.1)."""
	if not frappe.db.exists("Workspace Config", project):
		return  # a project without a workspace: the preflight names it
	cfg = frappe.get_doc("Workspace Config", project)
	row = next((s for s in cfg.sidebar_sections if s.section == "approvals"), None) \
		or cfg.append("sidebar_sections", {"section": "approvals", "visible": 1})
	if not row.client_visible:
		row.client_visible = 1
		cfg.save(ignore_permissions=True)  # the manager's own switch (set_switches checked them)


# --- approvers ----------------------------------------------------------------------------------------------------


def approvers(project: str) -> dict[str, bool]:
	"""A project's approvers (§2 rule 5), {user: confirmed}: each person's latest designation event, while they are a
	client contact of the project with an enabled account whose member row has may_approve (server-owned by ``guard``; a
	new row never carries it, so a removed and re-added contact is designated again). What the preflight and the answer
	path read."""
	latest = {body["user"]: body for _actor, body in _designations(project)}
	marked = set(frappe.get_all("Project Member", filters={"parenttype": PROJECT, "parent": project, "may_approve": 1},
		pluck="user"))
	contacts = marked.intersection(_contacts(project))
	return {u: b["state"] == CONFIRMED for u, b in latest.items() if b["may_approve"] == "1" and u in contacts}


def confirmed_projects(user: str, projects) -> set[str]:
	"""The projects among ``projects`` where ``user`` is a confirmed approver: ``approvers``' rule for one person across
	many projects, in at most two queries however many (P3-79, N11). What the Approvals tab's badge, the Home card and the
	chat's unread count read, so a contact still waiting for the second staff confirmation counts nothing. The caller is a
	signed-in client, so the account is enabled; test_approvals_portal holds this equal to ``approvers``."""
	if not (user and projects and is_client(user)):
		return set()
	marked = frappe.get_all("Project Member", filters={"parenttype": PROJECT, "parent": ["in", list(projects)],
		"user": user, "may_approve": 1}, pluck="parent")
	if not marked:
		return set()
	latest = {}
	for project, text in frappe.get_all("Approval Event", filters={"project": ["in", marked], "kind": "designation"},
			fields=["project", "canonical"], order_by="seq asc", as_list=True):
		body = json.loads(text)["body"]
		if body["user"] == user:
			latest[project] = body
	return {p for p, body in latest.items() if body["may_approve"] == "1" and body["state"] == CONFIRMED}


def on_project_update(doc, method=None):
	"""on_update of Construction Project: a member row removed while it had may_approve ends that designation in the
	chain too, with the session user as its actor, so the chain alone says who approves (§2 rule 5)."""
	before = doc.get_doc_before_save()
	kept = {r.user for r in doc.get("users") or []}
	for r in (before.get("users") or []) if before is not None else []:
		if cint(r.may_approve) and r.user not in kept:
			log.append_event(doc.name, "designation", body={"user": r.user, "may_approve": 0, "state": "",
				"authority": "", "authority_name": ""})


def _designations(project) -> list[tuple[str, dict]]:
	"""(actor, body) of each designation event of the project, oldest first."""
	rows = frappe.get_all("Approval Event", filters={"project": project, "kind": "designation"},
		fields=["actor", "canonical"], order_by="seq asc")
	return [(r.actor, json.loads(r.canonical)["body"]) for r in rows]


def _contacts(project) -> list[str]:
	"""The project's client contacts with an enabled account."""
	users = frappe.get_all("Project Member", filters={"parenttype": PROJECT, "parent": project}, pluck="user")
	return [u for u in users if u and is_client(u) and cint(frappe.db.get_value("User", u, "enabled"))]


def added_by(project: str, user: str) -> set[str]:
	"""Who added a client contact to the project (D-220): the sender of the invitation they joined by or, on an open
	link, the manager who let them in (its decider: whoever sent the link made it for anyone, and invites.decide keeps
	the sender from deciding while the project has two managers); for a contact added without an invitation, whoever
	saved the project when their row came (its change history), or the project's creator for a row the project was made
	with."""
	by = set(frappe.get_all("Access Invite", filters={"project": project, "account": user}, pluck="invited_by"))
	for r in frappe.get_all("Access Request", filters={"parenttype": "Access Invite", "account": user},
			fields=["parent", "decided_by"]):
		invite = frappe.db.get_value("Access Invite", r.parent, ["project", "invited_by"], as_dict=True)
		if invite and invite.project == project:
			by.add(r.decided_by or invite.invited_by)
	by -= {None, ""}
	if by:
		return by
	for v in frappe.get_all("Version", filters={"ref_doctype": PROJECT, "docname": project}, fields=["owner", "data"],
			order_by="creation desc"):
		added = json.loads(v.data or "{}").get("added") or []
		if any(isinstance(a, list) and a[:1] == ["users"] and isinstance(a[-1], dict) and a[-1].get("user") == user
				for a in added):
			return {v.owner}
	return {frappe.db.get_value(PROJECT, project, "owner")}


def _contact_row(doc, member):
	row = next((r for r in doc.get("users") or [] if r.name == member), None) if isinstance(member, str) else None
	if not row or not row.user or not is_client(row.user):
		raise frappe.PermissionError(_("Only a client contact of this project can approve."))
	return row


@frappe.whitelist(methods=["POST"])
def set_approver(project: str, member: str, may_approve: int | str = 1, authority_file: str | None = None) -> dict:
	"""Make one client contact of the project (its Project Member row) an approver, or not (§3.2 item 4):
	manage_clients. With two or more managers, one who added the contact does not designate them (D-220). An approver
	is confirmed at once while the project has another confirmed approver; otherwise they wait for a second staff member
	(confirm_approver). authority_file: an optional authority document, a File of this project, frozen. The answer lists
	the approvers and says when none is confirmed (``no_approver``)."""
	return log.retry_once(lambda: _set_approver(project, member, 1 if cint(may_approve) else 0, authority_file))


def _set_approver(project, member, may: int, authority_file) -> dict:
	doc = _project(project, "manage_clients")
	row = _contact_row(doc, member)
	if may and not cint(frappe.db.get_value("User", row.user, "enabled")):
		frappe.throw(_("This account is turned off."))
	if may and frappe.session.user in added_by(doc.name, row.user) and len(invites._managers(doc)) >= 2:
		frappe.throw(_("Another manager of this project designates the contacts you added."), frappe.PermissionError)
	sha, name = _freeze_file(doc.name, authority_file) if authority_file else ("", "")
	if not may:
		state = ""
	elif cint(row.may_approve):
		state = row.approver_state
	else:  # the first approver, while no other is confirmed, waits for a second staff member (D-427)
		state = CONFIRMED if any(c for u, c in approvers(doc.name).items() if u != row.user) else WAITING
	if _approver(row) == (may, state) and not sha:
		return _answer(doc.name)
	row.may_approve, row.approver_state = may, state
	_save(doc)
	log.append_event(doc.name, "designation", body={"user": row.user, "may_approve": may, "state": state,
		"authority": sha, "authority_name": name})
	_mail_contacts(doc)
	return _answer(doc.name)


@frappe.whitelist(methods=["POST"])
def confirm_approver(project: str, member: str) -> dict:
	"""A second staff member confirms an approver waiting for confirmation (§3.2 item 4, D-427): another manager of the
	project (manage_clients) or a System Manager, never the one who designated them."""
	return log.retry_once(lambda: _confirm_approver(project, member))


def _confirm_approver(project, member) -> dict:
	doc = _project(project, "read" if "System Manager" in frappe.get_roles() else "manage_clients")
	row = _contact_row(doc, member)
	if _approver(row) != (1, WAITING):
		frappe.throw(_("This contact is not waiting for confirmation."))
	designated = [actor for actor, body in _designations(doc.name) if body["user"] == row.user
		and body["may_approve"] == "1"]
	if not designated or designated[-1] == frappe.session.user:
		frappe.throw(_("A second staff member confirms an approver, not the one who designated them."),
			frappe.PermissionError)
	row.approver_state = CONFIRMED
	_save(doc)
	log.append_event(doc.name, "designation", body={"user": row.user, "may_approve": 1, "state": CONFIRMED,
		"authority": "", "authority_name": ""})
	_mail_contacts(doc)
	return _answer(doc.name)


def _answer(project) -> dict:
	found = approvers(project)
	return {"approvers": [{"user": u, "full_name": get_fullname(u), "state": CONFIRMED if c else WAITING}
		for u, c in found.items()], "no_approver": not any(found.values())}


def _mail_contacts(doc):
	"""Every client contact of the project gets the full approver list (§3.2 item 4, §6: no approver is added quietly)."""
	waiting = _("waiting for confirmation")
	lines = [f"{get_fullname(u)} ({_email(u)})" + ("" if c else f" - {waiting}") for u, c in approvers(doc.name).items()]
	_mail([_email(u) for u in _contacts(doc.name)], _("Approvers changed for {0}").format(doc.project_name), [
		_("{0} changed who can approve for {1} on the portal. The approvers are now:").format(
			get_fullname(frappe.session.user), doc.project_name),
		*(lines or [_("No one.")]), _("If this is not what you agreed with the team, tell them now.")])


# --- sending a record for approval (§3.4) -------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def request(doctype: str, name: str, due_date: str | None = None, note: str | None = None,
		work_started: str | None = None) -> dict:
	"""Send a Variation, Submittal, Document or Decision to its project's approvers (§3.4): request_client_approval, and
	approve_variation for a Variation or a priced Decision; the preflight, with the record's own state and visibility
	checked inside the lock; a due date (5 working days by default, D-379) and an optional note; for a Variation, whether
	work has started ("not_started" or the day it did). The terms and their cleaned frozen copies are frozen into an Open
	request (log.open_request). It links to the record's previous request, and one still Open or Approved is superseded
	with this one named in its place (C1). The card and the emails come with P3-78. P3-82 (§14.3): the record kind's route
	is frozen with the request (approvals.routes); when a before-client step applies, the request starts In internal
	review, staff-only, and the client is asked only once its last before-client step passes."""
	return log.retry_once(lambda: _request(doctype, name, due_date, note, work_started))


def _request(doctype, name, due_date, note, work_started) -> dict:
	from construction_core.approvals import routes  # here: routes imports this module's callers
	from construction_core.approvals.preflight import preflight  # here: preflight imports this module
	from construction_core.discuss.parts.file_requests import _due_on, _text

	if doctype not in subjects.SUBJECTS or not isinstance(name, str) or not frappe.db.exists(doctype, name):
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.get_doc(doctype, name).check_permission("read")  # before any lock
	log._lock_subject(doctype, name)  # the subject, then the project (D-459)
	doc = frappe.get_doc(doctype, name)
	log.lock(doc.project)
	frappe.has_permission(PROJECT, "request_client_approval", doc=doc.project, throw=True)
	if doctype == subjects.VO or (doctype == subjects.DECISION and subjects.priced(doc)):
		frappe.has_permission(subjects.VO, "approve_variation", doc=doc if doctype == subjects.VO else None, throw=True)
	reasons = preflight(doc.project, doctype, name)
	if reasons:
		frappe.throw("<br>".join(r["reason"] for r in reasons), title=_("This cannot be sent for approval yet"))
	due, note = _due_on(due_date), _text(note or "", NOTE_MAX)
	if doctype == subjects.VO:
		doc.db_set("work_started_on", _work_started(work_started))
	entries = subjects.freeze(doctype, name)
	prev = next(iter(subjects.requests_of(doctype, name)), None)
	covered = doc.decision_request if doctype == subjects.VO and subjects.decision_covers(doc) else ""
	route = routes.resolve(doc, routes.terms_for(doc), covered)
	internal = routes.starts_internal(route)
	if doctype == subjects.DECISION:
		doc.db_set("status", log.INTERNAL if internal else "Waiting")
	new = log.open_request(doc.project, doctype, name, frozen_entries=entries, subject_title=doc.title, due_date=due,
		note=note, predecessor=prev.name if prev else None, internal=internal)
	if route:
		log.append_event(doc.project, "route_frozen", request=new, body=route)  # §14.2: a later edit never reaches it
	if prev and prev.status in ("Open", "Approved", log.INTERNAL):
		subjects.supersede(prev, "Sent again", successor=new)
	elif prev and not prev.successor:
		subjects.name_successor(prev.name, new)
	r = frappe.get_doc(log.REQUEST, new)
	if internal:
		routes.started(new)  # the first step's people rung; no client email until it passes (§14.3 items 1, 4)
	else:
		_client_mail(r, _confirmed(r.project), _("{0} asks you to approve {1}").format(_lead(), _what(r)), REQUEST_MAIL,
			facts=_facts(r))  # M10: the request email (P3-77 wrote only its chain event)
	return {"request": new, "due_date": str(due), "internal": internal}


def _work_started(value):
	"""A Variation's "Has work started?" (§3.1): None for not started, else the day it started, never in the future."""
	if value == "not_started":
		return None
	try:
		day = getdate(value) if isinstance(value, str) and value else None
	except Exception:
		day = None
	if not day or day > getdate():
		frappe.throw(_("Say whether work has started: not started, or the day it started"))
	return day


@frappe.whitelist(methods=["POST"])
def make_variation(decision: str) -> dict:
	"""Make the variation of a decided priced Decision (§3.3): a new Variation (Potential Change) with one line from the
	chosen option, its days, the approved VAT basis, and its approval named (decision_request), which covers the
	Variation's gate while its total change, days, currency and VAT basis equal the frozen ones
	(subjects.decision_covers). Refused when the Decision's currency is not the Variation's. Once per approval."""
	return log.retry_once(lambda: _make_variation(decision))


def _make_variation(decision) -> dict:
	if not isinstance(decision, str) or not frappe.db.exists(subjects.DECISION, decision):
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.get_doc(subjects.DECISION, decision).check_permission("read")  # before the lock
	d = frappe.get_doc(subjects.DECISION, decision, for_update=True)  # one variation per approval, made one at a time
	approved = subjects.requests_of(subjects.DECISION, d.name, status="Approved")
	option = subjects.chosen(approved[0].name) if d.status == "Decided" and approved else None
	if not option or not (flt(option["cost_difference"]) or cint(option["time_difference"])):
		frappe.throw(_("Only a decided Decision whose chosen option changes the price or the time makes a variation"))
	why = subjects.unrelied(approved[0].name, True)  # M9: disputed, to re-confirm, or given by phone
	if why:
		frappe.throw(why)
	if frappe.db.exists(subjects.VO, {"decision_request": approved[0].name}):
		frappe.throw(_("The variation of this decision was made already"))
	terms = json.loads(approved[0].snapshot)["terms"]  # the basis the client approved
	if terms["currency"] != subjects.currency_of(d.project):
		frappe.throw(_("This decision is priced in {0} and the project's approved bill of quantities in {1}, so it cannot "
			"make a variation").format(terms["currency"], subjects.currency_of(d.project)))
	vo = frappe.get_doc({"doctype": subjects.VO, "project": d.project, "title": d.title, "reason": "Client Request",
		"amounts_include_vat": cint(terms["amounts_include_vat"]),
		"time_extension_days": cint(option["time_difference"]), "decision_request": approved[0].name,
		"deltas": [{"description": f"{d.title}: {option['label']}", "qty_delta": 1,
			"rate_delta": flt(option["cost_difference"]), "uom": "lot"}]})
	vo.flags.cc_decision = True  # the controller lets this module set decision_request
	vo.insert()  # as the caller: Variation Order's create permission and the project scope
	return {"variation": vo.name}


# --- staff acts on an open request: void and Nudge (§3.4, §3.10; M12) -------------------------------------------------


def _staff_request(request):
	"""The request, for staff of its project who send requests (request_client_approval)."""
	r = read.readable(request)
	if not r:
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.has_permission(PROJECT, "request_client_approval", doc=r.project, throw=True)
	return r


@frappe.whitelist(methods=["POST"])
def void(request: str, reason: str, note: str | None = None) -> dict:
	"""Staff void an Open request (§3.4): a reason from VOID_REASONS and optional words, shown to the client and mailed
	to the approvers (subjects.void). P3-82: one In internal review too ("close it" after a Return, §14.3 item 3),
	which no client ever saw, so nothing is mailed."""
	r = _staff_request(request)
	if reason not in VOID_REASONS:
		frappe.throw(_("Choose why the request is voided"))
	note = cstr(note).strip()[:NOTE_MAX]

	def _void() -> dict:
		log._lock_subject(r.subject_doctype, r.subject_name)  # first (D-459): a Waiting Decision then needs a new request
		row = frappe._dict(log.lock(r.project, r.name))
		if log.state_of(r.name) not in ("Open", log.INTERNAL):
			frappe.throw(_("Only a request still waiting for the client can be voided"))
		subjects.void(row, f"{reason}: {note}" if note else reason)
		return {"state": "Voided"}

	return log.retry_once(_void)


@frappe.whitelist(methods=["POST"])
def nudge(request: str) -> dict:
	"""Staff remind the approvers of an Open request now (§3.10, P3-71): each reminder counts toward the client limit
	(file_requests.CAPS, the daily reminders included); refused when every approver is at it. P3-82 (§14.3 item 8): an
	internal step waiting rings its people instead."""
	from construction_core.approvals import routes  # here: routes imports this module's callers
	from construction_core.approvals.preflight import preflight  # here: preflight imports this module

	r = _staff_request(request)

	def _nudge() -> dict:
		log.lock(r.project, r.name)
		state = log.state_of(r.name)
		stepped = routes.nudge(r) if state in (log.INTERNAL, "Approved") else None
		if stepped is not None:
			return {"reminded": stepped}
		if state != "Open":
			frappe.throw(_("Only a request still waiting for the client can be nudged"))
		reasons = preflight(r.project)
		if reasons:
			frappe.throw("<br>".join(x["reason"] for x in reasons), title=_("The client cannot answer yet"))
		reminded = _remind(r, "nudge")
		if not reminded:
			frappe.throw(_("Each approver has had {0} reminders for this request, the most we send. Message them in the "
				"Client room instead.").format(_client_cap()))
		return {"reminded": [get_fullname(u) for u in reminded]}

	return log.retry_once(_nudge)


# --- the evidence mailbox -----------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def set_evidence_mailbox(address: str) -> dict:
	"""The site's evidence mailbox (§3.2 item 3), by a System Manager: recorded in the chain of every project that has one
	(a later chain starts with the mailbox in force, in its settings event) and mailed to the old and the new address, the
	new one with a confirm link that works once, for TOKEN_HOURS. Unconfirmed until that link is used."""
	frappe.only_for("System Manager")
	address = cstr(address).strip()
	if not address or validate_email_address(address) != address:
		frappe.throw(_("Give exactly one email address"))
	return log.retry_once(lambda: _set_mailbox(address))


def _set_mailbox(address) -> dict:
	s = frappe.get_doc(SETTINGS, SETTINGS, for_update=True)
	old = s.evidence_mailbox or ""
	if address == old and cint(s.evidence_mailbox_confirmed):
		return _mailbox(s)
	token = secrets.token_urlsafe(32)
	s.update({"evidence_mailbox": address, "evidence_mailbox_confirmed": 0, "evidence_token_hash": _token_hash(token,
		address), "evidence_token_expires": add_to_date(now_datetime(), hours=TOKEN_HOURS)})
	_save(s)
	_mailbox_event({"address": address, "previous": old, "confirmed": 0})
	words = _("The evidence mailbox for client approvals changed from {0} to {1}.").format(old or _("none"), address)
	if old:
		_mail([old], _("The evidence mailbox changed"), [words])
	_mail([address], _("Confirm the evidence mailbox"), [words, _("Confirm that this mailbox receives the approval "
		"records. The link works once, for {0} hours.").format(TOKEN_HOURS)],
		link=(get_url(f"/evidence-mailbox#k={token}"), _("Confirm the mailbox")))
	return _mailbox(s)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def confirm_evidence_mailbox(token: str) -> dict:
	"""The confirm link's button (www/evidence-mailbox posts the token from the link's fragment): the token of the
	address it was sent to, once, before it expires. Recorded as ``set_evidence_mailbox`` records a change."""
	return log.retry_once(lambda: _confirm_mailbox(token))


def _confirm_mailbox(token) -> dict:
	s = frappe.get_doc(SETTINGS, SETTINGS, for_update=True)
	digest, expires = s.evidence_token_hash or "", s.evidence_token_expires
	if not (isinstance(token, str) and token and digest and expires and get_datetime(expires) > now_datetime()
			and hmac.compare_digest(_token_hash(token, s.evidence_mailbox or ""), digest)):
		raise frappe.PermissionError(_("This link does not work. Ask for a new test message."))
	s.update({"evidence_mailbox_confirmed": 1, "evidence_token_hash": "", "evidence_token_expires": None})
	_save(s)
	_mailbox_event({"address": s.evidence_mailbox, "previous": s.evidence_mailbox, "confirmed": 1})
	return _mailbox(s)


def _token_hash(token: str, address: str) -> str:
	return canonical.sha256(f"{address}\n{token}")  # bound to the address it was sent to


def _mailbox(s) -> dict:
	return {"address": s.evidence_mailbox or "", "confirmed": bool(cint(s.evidence_mailbox_confirmed))}


def _mailbox_event(body: dict):
	"""A mailbox change is a chain event in every project that has a chain (§3.2 item 3), in name order, the lock order.
	A project with none gets none: an event would make it undeletable (D-092). Its first settings event holds the mailbox
	in force (``_set_switches``). Known limit: a first settings event committed during this change keeps the old address;
	upgrade by reading the mailbox under a lock there, which reverses this lock order."""
	for project in frappe.get_all(log.EVENT, pluck="project", distinct=True, order_by="project"):
		log.append_event(project, "evidence_mailbox", body=body)


# --- mail ---------------------------------------------------------------------------------------------------------


def _email(user: str) -> str:
	return frappe.db.get_value("User", user, "email") or user


def _mail(recipients: list[str], subject: str, lines: list[str], link: tuple[str, str] | None = None):
	"""One set-up mail: plain lines, an optional link, the credit (D-402). Logged, never raised, when it cannot be queued.
	A mail with a link is redacted from the Email Queue once sent, as onboarding's are: the link is a secret."""
	if not recipients:
		return
	body = "".join(f"<p>{escape_html(line)}</p>" for line in lines)
	if link:
		body += f'<p><a href="{escape_html(link[0])}">{escape_html(link[1])}</a></p>'
	try:
		frappe.sendmail(recipients=recipients, subject=subject, message=body + credit_html(), now=True,
			redact_message_after_send=bool(link))
	except Exception as e:
		# a message of our own: with none, Frappe stores the traceback with its frames' values, the confirm link included
		frappe.log_error(title="construction_core: an approvals set-up mail could not be queued",
			message=f"{type(e).__name__}: subject {subject!r} to {', '.join(recipients)}", defer_insert=True)


# --- client notices and the staff bell (§3.10, §3.13; M10, L6) -------------------------------------------------------


def _lead() -> str:
	return brand() or _("The project team")  # the firm leads once its name is set (D-401)


def _what(r) -> str:
	from construction_core.approvals.receipts import what  # here: receipts imports this module

	return what(r)


def _confirmed(project) -> list[str]:
	return [u for u, ok in approvers(project).items() if ok]


def _portal_link(r) -> str:
	"""Through the portal's sign-in to the request's sheet, by ids only (as file_requests.sign_in_link)."""
	target = f"/portal/{quote(r.project, safe='')}?" + urlencode({"tab": "approvals", "request": r.name})
	return get_url("/portal/login?redirect-to=" + quote(target, safe=""))


def _facts(r) -> list[tuple[str, str]]:
	"""What the request asks, from its frozen terms (§3.13: the first client emails with record content)."""
	from construction_core.approvals.agreement import _change  # here: agreement imports this module

	terms, facts = json.loads(r.snapshot)["terms"], []
	if r.subject_doctype == subjects.VO:
		facts.append((_("Cost and time"), _change(terms["currency"], terms["total"], terms["days"])))
	elif r.subject_doctype == subjects.DECISION:
		facts += [(_("Option"), f'{o["label"]}: {_change(terms["currency"], o["cost_difference"], o["time_difference"])}')
			for o in terms.get("options") or []]
	elif r.subject_doctype in subjects.SUBJECTS:
		facts.append((_("Revision"), str(terms.get("revision") or "-")))
	if r.due_date:
		facts.append((_("Due date"), f"{getdate(r.due_date):%d %b %Y}"))
	if r.note:
		facts.append((_("Note from the team"), r.note))
	names = [get_fullname(u) for u in _confirmed(r.project)]
	if names:
		facts.append((_("Who can approve"), _("{0}. The first answer decides.").format(", ".join(names))))
	return facts


def _client_mail(r, users: list[str], subject: str, template: str, **args) -> list[str]:
	"""One client email about a request (M10): the firm's brand first, the record's content, a link to the portal and
	no frozen copy. Queued with the transaction, so a rollback drops it. Returns the users it went to; a mail that
	cannot be queued is logged and returns none."""
	if not users:
		return []
	project = frappe.db.get_value(PROJECT, r.project, "project_name")
	html = frappe.render_template(template, {**_brand_args(), "project": project, "what": _what(r),
		"link": _portal_link(r), "lead": "", "facts": [], **args})
	try:
		frappe.sendmail(recipients=[_email(u) for u in users], subject=subject, message=html, add_unsubscribe_link=0,
			now=False)
	except Exception as e:
		frappe.log_error(title="construction_core: an approval email could not be queued",
			message=f"{type(e).__name__}: {subject!r} for {r.name}", defer_insert=True)
		return []
	return users


def tell(r, kind: str, reason: str = "") -> None:
	"""The approvers mailed what to do when a request is superseded or voided (§3.10), or when its final record changed
	after the approval (L6, which also rings the managers' bell). Each caller does it once per event. P3-82: never for a
	request that did not reach the client (approvals.read.asked): its approvers never heard of it."""
	if not read.asked(r.name):
		return
	r = frappe.get_doc(log.REQUEST, r.name)
	what, lead = _what(r), _lead()
	if kind == "changed":
		notify(invites._managers(frappe.get_doc(PROJECT, r.project)), APPROVAL_CHANGED, r)
		subject, lines = _("{0} changed after your approval").format(what), [
			_("{0} changed {1} after you approved it.").format(lead, what),
			_("Your approval stays with the version you approved. The team will ask you again if a new approval is needed.")]
	elif kind == "voided":
		subject, lines = _("{0} was voided. Nothing needed now").format(what), [
			_("{0} voided the approval request for {1}: {2}.").format(lead, what, reason), _(NOTHING_NEEDED)]
	else:
		subject, lines = _("{0} was replaced. Nothing needed now").format(what), [
			_("{0} replaced the approval request for {1}.").format(lead, what), _(NOTHING_NEEDED)]
	_client_mail(r, _confirmed(r.project), subject, NOTICE_MAIL, lines=lines)


def answered(r, kind: str, actor: str) -> None:
	"""The staff bell "Client answered" (§3.13): to the requester and the project's managers, one kind for Approved and
	one for Returned; never mailed (D-160, D-175). ``actor``: the approver who gave it."""
	doc = frappe.get_doc(log.REQUEST, r.name)
	users = [doc.requester, *invites._managers(frappe.get_doc(PROJECT, doc.project))]
	notify([u for u in users if u != frappe.session.user], CLIENT_APPROVED if kind == "approved" else CLIENT_RETURNED,
		doc, actor=actor)


def _client_cap() -> int:
	from construction_core.discuss.parts.file_requests import CAPS

	return CAPS["client"]


def _remind(r, how: str) -> list[str]:
	"""A reminder of the request to each confirmed approver below the client limit, each a ``reminded`` chain event;
	reminder_1 and reminder_2 go once each, a Nudge whenever the limit allows. Inside the lock (project, then request),
	so the events read are the latest committed. Returns who was mailed."""
	r = frappe.get_doc(log.REQUEST, r.name)
	done = [json.loads(t)["body"] for t in frappe.db.sql("""select canonical from `tabApproval Event` where request = %s
		and kind = 'reminded' for update""", (r.name,), pluck=True)]
	due, today_ = getdate(r.due_date) if r.due_date else None, getdate(nowdate())
	if how == "reminder_1":
		lead = _("This is due tomorrow, {0}.").format(f"{due:%d %b %Y}")
	elif due and today_ > due:
		lead = _("This was due on {0}. You can still answer.").format(f"{due:%d %b %Y}")
	else:
		lead = _("A reminder from the team.")
	out = []
	for user in _confirmed(r.project):
		mine = [b["how"] for b in done if b["user"] == user]
		if len(mine) >= _client_cap() or (how != "nudge" and how in mine):
			continue
		if _client_mail(r, [user], _("Reminder: {0} asks you to approve {1}").format(_lead(), _what(r)), REQUEST_MAIL,
				lead=lead, facts=_facts(r)):
			log.append_event(r.project, "reminded", request=r.name, body={"user": user, "how": how})
			out.append(user)
	return out


def remind() -> int:
	"""Daily (hooks; §3.10, M10): reminder 1 the day before an Open request's due date, reminder 2 two working days after
	it (file_requests.working_days_after), and the requester's bell once it is overdue. One request that fails never
	stops the others. Returns how many reminders went."""
	today_ = getdate(nowdate())
	sent = 0
	for name in frappe.get_all(log.REQUEST, filters={"status": "Open", "due_date": ["<=", add_days(today_, 1)]},
			pluck="name", order_by="due_date asc"):
		point = "cc_approval_remind_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(point)
		try:
			sent += _remind_due(name, today_)
		except Exception:
			frappe.db.rollback(save_point=point)
			frappe.log_error(title="construction_core: approval reminders failed", reference_doctype=log.REQUEST,
				reference_name=name)
		else:
			frappe.db.release_savepoint(point)
	return sent


def _remind_due(name: str, today_) -> int:
	from construction_core.approvals.preflight import preflight  # here: preflight imports this module
	from construction_core.discuss.parts.file_requests import working_days_after

	r = frappe._dict(log.lock(frappe.db.get_value(log.REQUEST, name, "project"), name))
	if log.state_of(name) != "Open" or not r.due_date or preflight(r.project):
		return 0  # moved on, or closed to the client: nothing to remind of
	due = getdate(r.due_date)
	if today_ > due and not frappe.db.exists("Notification Log", {"for_user": r.requester,
			"document_type": log.REQUEST, "document_name": name, "email_header": key(APPROVAL_OVERDUE)}):
		notify([r.requester], APPROVAL_OVERDUE, frappe.get_doc(log.REQUEST, name))  # once, when it becomes overdue
	how = "reminder_1" if today_ == add_days(due, -1) else "reminder_2" if today_ == working_days_after(due, 2) else ""
	return len(_remind(r, how)) if how else 0
