"""P3-16 (R-13; D-187, D-188, D-192, D-195, D-209): invitations, as the project team makes and follows them.

A link is `https://<site>/join#k=<token>`: 32 random bytes in the URL fragment, so the token never reaches a server,
a log or a Referer; only its sha256 is stored, so a link is shown once (with a QR). A bound invitation has two links
(D-219): the one the team copies or shows (the code proves the address) and one that is only ever mailed to that
address (opening it proves the inbox). A new link (renew) kills both old ones. An open link's people each have an
Access Request; a manager approves or declines them (`decide`, P3-18, D-220). Every method checks permission in its own body (DR-5): making,
renewing, revoking and editing need the project's `manage_clients`; reading needs a team member who reads the
project. Access Invite and Client Profile are System Manager only; this module writes them with ignore_permissions
after its own checks. No answer ever carries a token, its hash or a code.
"""

import hashlib
import re
import secrets

import frappe
from frappe import _
from frappe.utils import (add_days, add_to_date, cint, get_datetime, get_fullname, get_url, now_datetime, nowdate,
	validate_email_address)

from construction_core.onboarding import mail
from construction_core.permissions import CLIENT_ROLE, is_client, refuse_closed

BOUND_DAYS, OPEN_DAYS = 7, 3  # D-195
RENEWALS_A_DAY = 5
RESERVED = ("Administrator", "Guest")
SEPARATORS = re.compile(r"[,;\s]")
UNSAFE = re.compile(r"[<>\u0000-\u001f\u007f‪-‮⁦-⁩]")
PUBLIC_INVITE = ("name", "kind", "email", "full_name", "job_title", "status", "expires_on", "mail_state", "invited_by",
	"creation")
PUBLIC_REQUEST = ("name", "email", "full_name", "mobile_no", "company_name", "status", "verified_on")


def token_hash(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def link_for(token: str) -> str:
	return get_url(f"/join#k={token}")


def qr_for(link: str) -> str:
	from frappe.twofactor import get_qr_svg_code

	svg = get_qr_svg_code(link)
	return "data:image/svg+xml;base64," + (svg.decode() if isinstance(svg, bytes) else svg)


def _plain(value, limit=140) -> str | None:
	"""Text a person typed, kept plain: no markup brackets, control or direction characters, at most `limit`."""
	text = UNSAFE.sub("", str(value or "")).strip()[:limit]
	return text or None


def _clean_email(email: str) -> str:
	email = (email or "").strip().lower()
	if not email or SEPARATORS.search(email) or validate_email_address(email, throw=False) != email:
		frappe.throw(_("Enter one email address, for example maria.santos@example.com."))
	return email


def _project(project: str, ptype: str = "manage_clients"):
	doc = frappe.get_doc("Construction Project", project)
	frappe.has_permission("Construction Project", ptype, doc=doc, throw=True)
	return doc


def _team_reader(project: str):
	"""A team member who reads the project (never a client)."""
	if is_client(frappe.session.user):
		raise frappe.PermissionError(_("This is for the project team"))
	return _project(project, "read")


def _members(doc) -> set[str]:
	return {r.user for r in doc.get("users") or []}


def effective_status(invite) -> str:
	if invite.status == "Active" and invite.expires_on and get_datetime(invite.expires_on) < now_datetime():
		return "Expired"
	return invite.status


def _check_address(email: str, doc, renewing: str | None = None):
	"""Refuse an address that cannot become this project's client (D-188): the team, reserved, turned-off or present."""
	if email in RESERVED:
		frappe.throw(_("This address cannot be invited."), frappe.PermissionError)
	account = frappe.db.get_value("User", {"name": email}, ["name", "user_type", "enabled"], as_dict=True) or \
		frappe.db.get_value("User", {"email": email}, ["name", "user_type", "enabled"], as_dict=True)
	if account:
		if account.name in RESERVED or account.user_type != "Website User":
			frappe.throw(_("This address belongs to a team account."), frappe.PermissionError)
		if not cint(account.enabled):
			frappe.throw(_("This account is turned off. Ask an administrator."), frappe.PermissionError)
		if account.name in _members(doc):
			frappe.throw(_("This person is already a client contact of this project."))
	waiting = frappe.get_all("Access Invite", filters={"project": doc.name, "email": email, "status": "Active",
		"expires_on": (">", now_datetime()), "name": ("!=", renewing or "")}, pluck="name")
	if waiting:
		frappe.throw(_("An invitation to this address is already waiting. Send a new link instead."))


def _require_mail():
	if not mail.mail_ready():
		frappe.throw(_("Email isn't set up yet. Ask your administrator to set up the company's email first."))


def _expiry(email) -> str:
	return add_days(now_datetime(), BOUND_DAYS if email else OPEN_DAYS)


def _share(invite, token: str, mail_token: str | None, mail_it) -> dict:
	link = link_for(token)
	emailed = False
	if invite.email and mail_token and cint(mail_it):
		emailed = mail.send_invite(invite, link_for(mail_token))  # the mailed link: opening it proves the inbox (D-219)
		invite.db_set("mail_state", "Queued" if emailed else "Failed", update_modified=False)
	return {"invite": invite.name, "link": link, "qr": qr_for(link), "expires_on": str(invite.expires_on),
		"emailed": emailed, "bound": bool(invite.email)}


@frappe.whitelist(methods=["POST"])
def create_invite(project: str, email: str | None = None, full_name: str | None = None, job_title: str | None = None,
		mail_it: int | str = 1) -> dict:
	"""A client invitation to `project`: bound to `email` when given (7 days), open otherwise (3 days, D-195)."""
	doc = _project(project)
	refuse_closed(doc.name)
	_require_mail()
	email = _clean_email(email) if (email or "").strip() else None
	if email:
		_check_address(email, doc)
	token = secrets.token_urlsafe(32)
	mail_token = secrets.token_urlsafe(32) if email else None
	invite = frappe.get_doc({
		"doctype": "Access Invite", "kind": "Client", "project": doc.name, "role": CLIENT_ROLE, "email": email,
		"full_name": _plain(full_name), "job_title": _plain(job_title), "status": "Active",
		"expires_on": _expiry(email), "token_hash": token_hash(token),
		"mail_token_hash": token_hash(mail_token) if mail_token else None, "invited_by": frappe.session.user,
		"mail_state": "Not sent",
	})
	invite.insert(ignore_permissions=True)  # System Manager-only doctype; manage_clients was checked above
	return _share(invite, token, mail_token, mail_it)


def _locked(invite: str):
	"""The invitation, locked for this transaction, and its project checked for manage_clients."""
	if not frappe.db.exists("Access Invite", invite):
		raise frappe.DoesNotExistError(_("No such invitation"))
	inv = frappe.get_doc("Access Invite", invite, for_update=True)  # with its requests, the latest committed (D-222)
	if inv.kind != "Client":
		raise frappe.PermissionError(_("A team invitation is managed on the People page."))  # P3-21 (D-235)
	_project(inv.project)
	return inv


@frappe.whitelist(methods=["POST"])
def renew(invite: str, mail_it: int | str = 1) -> dict:
	"""A new link for an invitation that has not been used: the old link stops working, the expiry starts again."""
	inv = _locked(invite)
	refuse_closed(inv.project)
	if inv.status in ("Used", "Revoked"):
		frappe.throw(_("This invitation can no longer be renewed."))
	if inv.email:  # the address may have become a team account, turned off or a contact since (P3-16 audit)
		_check_address(inv.email, frappe.get_doc("Construction Project", inv.project), renewing=inv.name)
	_require_mail()
	today = nowdate()
	count = cint(inv.renewals) if str(inv.renewed_on or "") == today else 0
	if count >= RENEWALS_A_DAY:
		frappe.throw(_("This invitation was renewed {0} times today. Try again tomorrow.").format(RENEWALS_A_DAY))
	token = secrets.token_urlsafe(32)
	mail_token = secrets.token_urlsafe(32) if inv.email else None
	inv.update({"token_hash": token_hash(token), "mail_token_hash": token_hash(mail_token) if mail_token else None,
		"status": "Active", "expires_on": _expiry(inv.email), "renewals": count + 1, "renewed_on": today,
		"codes_sent": 0, "mail_state": "Not sent"})
	_unprove(inv)  # a new link starts unproven: no check of the old one carries over (P3-17 audit M1)
	inv.save(ignore_permissions=True)
	return _share(inv, token, mail_token, mail_it)


def _unprove(inv):
	"""Drop every code and every address check of an invitation's requests; their approvals and joins stay."""
	for r in inv.requests:
		r.update({"code_hmac": None, "code_expires_on": None, "code_tries": 0, "codes_sent": 0, "verified_until": None,
			"proof_hash": None})


@frappe.whitelist(methods=["POST"])
def revoke(invite: str) -> dict:
	inv = _locked(invite)
	if inv.status == "Used":
		frappe.throw(_("This invitation has been used; remove the contact instead."))
	inv.update({"status": "Revoked", "revoked_by": frappe.session.user, "revoked_on": now_datetime()})
	_unprove(inv)
	for r in inv.requests:
		if r.status == "Approved":
			r.update({"finish_token_hash": None, "finish_expires_on": None})  # a revoke ends approved links too
	inv.save(ignore_permissions=True)
	return {"invite": inv.name, "status": inv.status}


FINISH_HOURS = 48  # D-220: the single-use link a person gets once a manager approves them


def _managers(project) -> list[str]:
	from construction_core.discuss.api import staff_members

	return [u for u in staff_members(project.name) if cint(frappe.db.get_value("User", u, "enabled"))
		and frappe.has_permission("Construction Project", "manage_clients", doc=project, user=u)]


@frappe.whitelist(methods=["POST"])
def decide(invite: str, request_id: str, approve: int | str = 1) -> dict:
	"""Approve or decline one person waiting on an open link (D-188, D-220). manage_clients; when the project has two
	or more enabled managers, the one who sent the link may not approve its people."""
	inv = _locked(invite)
	if cint(approve):  # declining lets no one in, so it stays open after close
		refuse_closed(inv.project)
	row = next((r for r in inv.requests if r.name == request_id), None)
	if not row or row.status != "Waiting":
		frappe.throw(_("This request is not waiting for a decision."))
	if inv.status != "Active" or effective_status(inv) != "Active":
		frappe.throw(_("This link no longer works; send a new invitation."))
	project = frappe.get_doc("Construction Project", inv.project)
	user = frappe.session.user
	if cint(approve) and user == inv.invited_by and len(_managers(project)) >= 2:
		frappe.throw(_("Another manager of this project approves the people your own link brought."),
			frappe.PermissionError)
	row.update({"decided_by": user, "decided_on": now_datetime()})
	if not cint(approve):
		row.update({"status": "Declined", "verified_until": None, "code_hmac": None, "proof_hash": None})
		inv.save(ignore_permissions=True)
		return {"request": row.name, "status": row.status}
	from construction_core.onboarding import join

	if not join._usable(row.email):  # the join page's own test, by name or email (D-222)
		frappe.throw(_("This address belongs to a team account or a turned-off account."), frappe.PermissionError)
	account = join._account(row.email)
	if account:  # an existing client: the project is added now, and they are told
		join.add_member(inv, project, account.name, row)
		row.update({"status": "Joined", "account": account.name})
		inv.save(ignore_permissions=True)
		mail.send_access_added(row, row.email)
		return {"request": row.name, "status": row.status}
	token = secrets.token_urlsafe(32)
	row.update({"status": "Approved", "finish_token_hash": token_hash(token),
		"finish_expires_on": add_to_date(now_datetime(), hours=FINISH_HOURS)})
	inv.save(ignore_permissions=True)
	mail.send_finish(row, row.email, link_for(token))  # to the verified address only; never shown to the team
	return {"request": row.name, "status": row.status}


@frappe.whitelist(methods=["GET"])
def project_invites(project: str) -> dict:
	"""The project's invitations for its team, without any secret; open links carry their waiting requests."""
	doc = _team_reader(project)
	can_manage = frappe.has_permission("Construction Project", "manage_clients", doc=doc)
	out = []
	for name in frappe.get_all("Access Invite", filters={"project": doc.name, "kind": "Client"}, order_by="creation desc",
			pluck="name"):  # a team invitation naming the project is the People page's (D-235)
		inv = frappe.get_doc("Access Invite", name)
		row = {f: inv.get(f) for f in PUBLIC_INVITE}
		row["status"] = effective_status(inv)
		if inv.mail_state == "Queued":
			row["mail_state"] = mail.delivery(inv.name) or "Queued"  # the queue's own outcome (P3-16 audit S2)
		row["invited_by_name"] = get_fullname(inv.invited_by) if inv.invited_by else None
		# Only proven people: an address anyone typed on the link is not the team's to read (D-222).
		row["requests"] = [{f: r.get(f) for f in PUBLIC_REQUEST} for r in inv.requests if r.verified_on]
		out.append(row)
	return {"invites": out, "can_manage": bool(can_manage), "mail_ready": mail.mail_ready(),
		"company": mail.brand()}  # what the mails and the join page call the company (D-210, D-225)


@frappe.whitelist(methods=["GET"])
def client_details(project: str) -> list[dict]:
	"""The project's client contacts with what the team needs: the name the team sees, email, job title, mobile and
	company (Client Profile, D-209). For the team only; never on Project Member, which clients can list (D-105)."""
	doc = _team_reader(project)
	out = []
	for row in doc.get("users") or []:
		if not row.user or not is_client(row.user):
			continue
		profile = frappe.db.get_value("Client Profile", {"account": row.user}, ["full_name", "mobile_no",
			"company_name"], as_dict=True) or {}  # by account: a User rename leaves the record's name (audit S5)
		out.append({"member": row.name, "email": row.user, "job_title": row.job_title,
			"full_name": profile.get("full_name") or get_fullname(row.user), "mobile_no": profile.get("mobile_no"),
			"company_name": profile.get("company_name")})
	return out


@frappe.whitelist(methods=["POST"])
def update_client(project: str, member: str, full_name: str | None = None, mobile_no: str | None = None,
		company_name: str | None = None, job_title: str | None = None) -> dict:
	"""Edit one client contact of `project`, identified by its Project Member row; manage_clients (DR-5)."""
	doc = _project(project)
	row = next((r for r in doc.get("users") or [] if r.name == member), None)
	if not row or not row.user or not is_client(row.user):
		raise frappe.PermissionError(_("This is not a client contact of this project."))
	existing = frappe.db.get_value("Client Profile", {"account": row.user})
	profile = frappe.get_doc("Client Profile", existing) if existing else \
		frappe.get_doc({"doctype": "Client Profile", "account": row.user})
	for field, value, limit in (("full_name", full_name, 140), ("mobile_no", mobile_no, 40),
			("company_name", company_name, 140)):
		if value is not None:
			profile.set(field, _plain(value, limit))
	profile.save(ignore_permissions=True)  # System Manager-only doctype; manage_clients was checked above
	if job_title is not None and _plain(job_title) != row.job_title:
		row.job_title = _plain(job_title)
		doc.save()  # the members table is the managers' own permlevel-1 write
	return next(c for c in client_details(doc.name) if c["member"] == member)


def delete_project_invites(doc, method=None):
	"""Construction Project on_trash: its invitations go with it (they link to it)."""
	names = frappe.get_all("Access Invite", filters={"project": doc.name}, pluck="name")
	if names:
		frappe.db.sql("update `tabClient Profile` set joined_from = null where joined_from in %(names)s",
			{"names": names})  # a profile kept its link to the invitation (P3-16 audit S4)
		frappe.db.delete("Access Request", {"parenttype": "Access Invite", "parent": ("in", names)})
		frappe.db.delete("Access Invite", {"name": ("in", names)})
