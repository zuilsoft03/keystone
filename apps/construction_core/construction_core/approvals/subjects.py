"""What a client approves (approvals design §3.1, §3.3, §3.10, §3.11, §4.3; D-424, D-429): the four subject kinds and
what their saves do to their requests.

- **Terms** (§3.1): one builder per kind, registered with log: exactly the table's terms, in canonical values. Amounts
  are Decimals of fields stored at PLACES (their JSON precision makes their columns decimal(21,2); the controllers round
  each line first, so a total is its lines' sum), so the text never merges two stored amounts (C4); a quantity is its exact text; a date is a date (C5); each file shown is a row of
  ``terms["files"]``, its key and its original's SHA-256, never its File id. A Variation's currency is its project's
  approved BOQ's. A priced Decision's signatory is the requester, bound by the requested event (log.request_body), not
  the terms, which the gate and the daily check rebuild without a session.
- **Allowed** (§3.1): a request may be open while the record is in one of ``SUBJECTS[doctype].open`` and client visible
  (a Decision: while Waiting); log.open_request checks it again inside the lock (C6 locks the child rows there too).
- **Supersede** (§3.10): ``check`` runs first in each record's on_update, so the terms it reads are the saved ones, after
  the controller's own computation. A save that changes the terms of an Open or Approved request, or moves the record out
  of its allowed state, supersedes the request, but only when the caller confirms with REPLACE in the saved document
  (a Desk or REST save sends it as a key of the document; without it the save is refused with ReplaceRequest, and the
  shell asks the person and sends it again with REPLACE); an Approved request stays once the record is final, and a
  change of its terms (a System Manager's edit, or a file's) writes changed_after_decision, once per change.
  ``on_file_revised`` (an upload, a restore or an Office save, from versions.revise) needs no confirmation: the file
  changed. Never File events.
- **The gate** (§3.11): a staff move into GATED waits for the client while the record's client_approval_required and
  the project's Portal approvals are on: its latest request approved in the chain, on the terms saved now, and relied on
  (P3-78, M9 ``unrelied``: no open dispute, no re-confirmation due, no phone approval of a price or time change).
  client_approval_required cannot change once a request names the record.
- **Frozen copies** (§4.3): each file shown passes the client-file checks (type list, signature, structure and size)
  and the virus scan, and images are re-encoded (clean_image: no EXIF, XMP or GPS) before log.open_request stores them.
"""

import json
import mimetypes
import time
from dataclasses import dataclass
from decimal import Decimal

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate

from construction_core import client_files
from construction_core.approvals import canonical, frozen, log
from construction_core.construction_core.doctype.project_document.project_document import FINAL as DOC_FINAL
from construction_core.construction_core.doctype.submittal.submittal import FINAL as SUB_FINAL
from construction_core.construction_core.doctype.boq.boq import origin
from construction_core.construction_core.doctype.variation_order.variation_order import FINAL as VO_FINAL
from construction_core.construction_core.doctype.variation_order.variation_order import _origin_of, latest_approved_boq
from construction_core.files import versions
from construction_core.providers.storage import IMAGE_TYPES, clean_image

VO, SUB, DOC, DECISION = "Variation Order", "Submittal", "Project Document", "Client Decision"
PLACES = 2  # the precision of every amount the terms show (their JSON "precision")
REPLACE = "__replace_request"  # the caller's confirmation that a save replaces a request (§3.4)
NEEDS = "Needs a new request"
PHONE = "phone"  # a staff-recorded approval's method that never opens a priced gate (approvals.recorded, §3.9)


class ReplaceRequest(frappe.ValidationError):
	"""A save that replaces a request, sent without REPLACE: the shell asks the person, then sends it again with it."""


@dataclass(frozen=True)
class Subject:
	state: str  # the field holding the record's state
	send: tuple  # the states a request is sent from
	open: tuple  # the states a request may be open in (§3.1)
	gated: tuple  # the states a staff move into waits for the client (§3.11)
	final: tuple


SUBJECTS = {
	VO: Subject("stage", ("Change Order Request",), ("Change Order Request",), ("Approved Change",), tuple(VO_FINAL)),
	SUB: Subject("status", ("Submitted", "Under Review"), ("Submitted", "Under Review"), ("Approved", "Approved as Noted"),
		tuple(SUB_FINAL)),
	DOC: Subject("status", ("Client Review",), ("Client Review",), ("Published",), tuple(DOC_FINAL)),
	# P3-82: a Decision under internal review shows it (§14.3 item 1); Waiting starts when the client is asked
	DECISION: Subject("status", ("Draft", "Waiting", NEEDS, log.INTERNAL), ("Waiting", log.INTERNAL), (),
		("Decided", "Withdrawn", "Changed")),
}


def allowed(doc) -> bool:
	"""Whether a request may be open on the record now (§3.1): its allowed state, and client visible."""
	return doc.get(SUBJECTS[doc.doctype].state) in SUBJECTS[doc.doctype].open and (
		doc.doctype == DECISION or bool(cint(doc.get("client_visible"))))


def priced(decision) -> bool:
	"""A Decision with a cost or time difference (§3.3): sending it needs approve_variation."""
	return any(flt(o.cost_difference) or cint(o.time_difference) for o in decision.options)


# --- terms (§3.1) -----------------------------------------------------------------------------------------------------


def _doc(doctype, name):
	return name if isinstance(name, Document) else frappe.get_doc(doctype, name)


def _money(value) -> Decimal:
	return Decimal(str(flt(value)))  # C4: its column holds PLACES decimals (Frappe makes it decimal(21,2))


def _quantity(value) -> str:
	return format(Decimal(str(flt(value))).normalize(), "f")  # exact, never rounded onto another quantity


def _file_of(url, doc) -> str:
	"""An attached address's single File (§3.4): the record's project's, or, when the project has none there, the one
	with no project attached to the record itself (a Desk upload on it). A version row counts: a revised file's old
	content keeps its address there (D-305). An address in the bin, or held by another project's file, is refused."""
	rows = frappe.get_all("File", filters={"file_url": url, "is_folder": 0}, fields=["name", "cc_project", "cc_trashed",
		"attached_to_doctype", "attached_to_name"]) if url else []
	files = [r.name for r in rows if r.cc_project == doc.project] or [r.name for r in rows if not r.cc_project
		and (r.attached_to_doctype, r.attached_to_name) == (doc.doctype, doc.name)]
	if len(files) != 1 or any(r.cc_trashed or r.cc_project not in (None, "", doc.project) for r in rows):
		frappe.throw(_("Re-attach the file"), frappe.DoesNotExistError)
	return files[0]


def _shown(key, url, doc, sha_of) -> dict:
	return {"key": key, "sha256": sha_of(_file_of(url, doc))}


def _currency() -> str:
	return frappe.db.get_default("currency") or ""


def currency_of(project) -> str:
	"""A Variation's currency (§3.1): its project's approved BOQ's, else the site's."""
	boq = latest_approved_boq(project)
	return (boq and frappe.db.get_value("BOQ", boq, "currency")) or _currency()


def _variation(name, sha_of) -> dict:
	vo = _doc(VO, name)
	boq = latest_approved_boq(vo.project)
	# A line's terms are the approved BOQ line the approval applies the delta to (_create_boq_revision, by origin), never
	# the Draft copy a delta may name, which stays editable. Approved lines never change (BOQ._check_immutable) and the
	# delta rows naming them are locked with the subject (C6), so no lock of their own: one here would come before the
	# project's in open_request, against a variation approval's project-then-BOQ order.
	approved = {origin(l): l.description for l in frappe.get_all("BOQ Line", filters={"parenttype": "BOQ",
		"parent": boq}, fields=["name", "origin_line", "description"])} if boq else {}
	return {"title": vo.title or "", "description": canonical.plain(vo.description),
		"lines": [{"idx": d.idx, "quantity": _quantity(d.qty_delta), "description": (approved.get(_origin_of(d.boq_line))
			if d.boq_line else d.description) or "", "amount": _money(d.amount_delta)} for d in vo.deltas],
		"total": _money(vo.vo_delta_sum), "days": cint(vo.time_extension_days),
		"currency": currency_of(vo.project),
		"amounts_include_vat": cint(vo.amounts_include_vat),
		"work_start": getdate(vo.work_started_on) if vo.work_started_on else "Not started",
		"files": [_shown(f"a{r.idx}", r.file, vo, sha_of) for r in vo.attachments]}


def _submittal(name, sha_of) -> dict:
	s = _doc(SUB, name)
	rev = s.revisions[-1] if s.revisions else frappe._dict()
	return {"title": s.title or "", "revision": cint(rev.revision_no), "files": [_shown("file", rev.file, s, sha_of)]}


def _document(name, sha_of) -> dict:
	d = _doc(DOC, name)
	if not d.document_file:
		frappe.throw(_("Re-attach the file"), frappe.DoesNotExistError)
	return {"number": d.document_number or "", "revision": d.revision or "", "title": d.title or "",
		"file_rev": versions.current_rev(d.document_file), "files": [{"key": "file", "sha256": sha_of(d.document_file)}]}


def _decision(name, sha_of) -> dict:
	d = _doc(DECISION, name)
	return {"title": d.title or "", "category": d.category or "", "description": canonical.plain(d.description),
		"options": [{"idx": o.idx, "key": o.option_key, "label": o.label or "", "description": o.description or "",
			"file": o.option_key if o.file else "", "cost_difference": _money(o.cost_difference),
			"time_difference": cint(o.time_difference), "supplier": o.supplier or ""} for o in d.options],
		"recommended": d.recommended_option or "", "base_item": d.base_item or "", "currency": d.currency or _currency(),
		"amounts_include_vat": cint(d.amounts_include_vat),
		"files": [_shown(o.option_key, o.file, d, sha_of) for o in d.options if o.file]}


for _dt, _terms in ((VO, _variation), (SUB, _submittal), (DOC, _document), (DECISION, _decision)):
	log.register(_dt, _terms, PLACES, allowed)


# --- frozen copies (§4.3) ---------------------------------------------------------------------------------------------


def freeze(doctype: str, name: str) -> list[dict]:
	"""The cleaned frozen copy of each file the record's terms show, for log.open_request."""
	hashes = log.Hashes()
	entries = []
	started = time.monotonic()
	for row in log.terms_of(doctype, name, hashes).get("files") or []:
		f = frappe.get_doc("File", next(file for file, (_i, sha) in hashes.seen.items() if sha == row["sha256"]))
		content = frozen.original(f.name)
		ext = versions.split_name(f.file_name)[1].lstrip(".").lower()
		client_files.check_type(ext)
		client_files.check_signature(ext, content)
		client_files.check_structure(ext, content)  # and the type's size cap
		# as portal_api.send_file: a threat, or no scanner to ask, refuses the request; the files share the 120 s
		client_files.scan(content, project=f.cc_project or None,
			budget=max(5.0, 110.0 - (time.monotonic() - started)))
		if ext in IMAGE_TYPES:
			content = clean_image(content, ext)
		entries.append(frozen.freeze(content, key=row["key"], name=f.file_name, original_sha256=row["sha256"],
			ctype=(mimetypes.guess_type(f.file_name)[0] or "application/octet-stream").lower(),
			rev=f.cc_rev if f.cc_version_of else versions.current_rev(f.name)))
	return entries


# --- requests named by a record (§3.10) -------------------------------------------------------------------------------


FIELDS = ["name", "status", "project", "subject_doctype", "subject_name", "snapshot", "frozen_files", "terms_hash",
	"successor"]


def requests_of(doctype: str, name: str, **filters) -> list:
	"""The record's requests, newest first."""
	return frappe.get_all(log.REQUEST, filters={"subject_doctype": doctype, "subject_name": name, **filters},
		fields=FIELDS, order_by="creation desc")


def terms_hash(r) -> str | None:
	"""The terms_hash the record's saved terms would freeze with r's own shown copies and places (as log.terms_agree
	rebuilds them), or None when they cannot be built (a file to re-attach)."""
	try:
		terms = log.terms_of(r.subject_doctype, r.subject_name, log.Hashes())
		return canonical.sha256(log.snapshot_text(r.project, r.subject_doctype, r.subject_name, terms,
			json.loads(r.frozen_files), int(json.loads(r.snapshot)["places"])))
	except frappe.ValidationError:
		frappe.clear_last_message()
		return None


def supersede(r, reason: str, successor: str = "", doc=None) -> None:
	"""Open, Approved or In internal review (P3-82) to Superseded (§3.10). The body names the request sent in its place, when there is one (C1);
	without one a Waiting Decision needs a new request and the approvers are mailed (the new request's own email tells
	them when there is one). ``doc``: the record being saved, when it is."""
	from construction_core.approvals.api import tell  # here: api imports this module
	log.append_event(r.project, "superseded", request=r.name, body={"reason": reason, "successor": successor})
	if successor:
		name_successor(r.name, successor)
	else:
		_needs_new(r, doc)
		tell(r, "superseded")


def name_successor(request: str, successor: str) -> None:
	doc = frappe.get_doc(log.REQUEST, request)
	doc.successor = successor
	log._write(doc, "save")  # the one column a request's save may change besides its status


def void(r, reason: str, doc=None) -> None:
	"""An Open request voided (§3.10): Portal approvals turned off, a Decision withdrawn, staff (api.void). The approvers
	are mailed the reason."""
	from construction_core.approvals.api import tell  # here: api imports this module
	log.append_event(r.project, "voided", request=r.name, body={"reason": reason})
	_needs_new(r, doc)
	tell(r, "voided", reason)


def _needs_new(r, doc=None) -> None:
	if r.subject_doctype != DECISION:
		return
	doc = doc if doc is not None and doc.doctype == DECISION else frappe.get_doc(DECISION, r.subject_name)
	if doc.status in ("Waiting", log.INTERNAL):
		doc.db_set("status", NEEDS)  # the record being saved too: its form keeps the row's status and modified


def check(doc) -> None:
	"""on_update of the four subjects, first (§3.2, §3.10, §3.11): see the module's docstring."""
	before = doc.get_doc_before_save()
	if before is None:
		return  # a new record: no request names it
	s, rows = SUBJECTS[doc.doctype], requests_of(doc.doctype, doc.name)
	if rows and cint(before.get("client_approval_required")) != cint(doc.get("client_approval_required")):
		frappe.throw(_("Client approval stays as it was once the record was sent for approval"), frappe.PermissionError)
	state, was = doc.get(s.state), before.get(s.state)
	if state != was and state in s.gated:
		_gate(doc, rows[0] if rows else None)
	if was in s.final:  # only a System Manager edits a final record (its controller): the edit is recorded (L6)
		for r in rows:
			if r.status == "Approved":
				_changed_after_decision(r)
		return
	for r in rows:
		# P3-82: a change during internal review supersedes too, so its steps start over (§14.3 item 6)
		if r.status not in ("Open", "Approved", log.INTERNAL) or (r.status == "Approved" and state in s.final) \
				or (r.status == log.INTERNAL and state != was and state in s.gated):
			continue  # an approval stays with the decision it was for; a Variation's covered run once the gate let it by
		if allowed(doc) and terms_hash(r) == r.terms_hash:
			continue
		if doc.doctype == DECISION and state == "Withdrawn":
			void(r, "The decision was withdrawn", doc)
		elif not doc.get(REPLACE):
			frappe.throw(_("This record was sent to the client for approval, and this change replaces that request. "
				"Confirm to save it and send it again."), ReplaceRequest, title=_("Replace the approval request?"))
		else:
			supersede(r, "The terms changed" if allowed(doc) else f"The record moved to {state}", doc=doc)


def _gate(doc, latest) -> None:
	"""§3.11: refuses a staff move into GATED while ``gate_reason`` says why."""
	why = gate_reason(doc, latest)
	if why:
		frappe.throw(why, title=_("Client approval"))


def gate_reason(doc, latest) -> str:
	"""§3.11, L4, M9: "" when the move may go ahead: the latest request approved in the chain on the saved terms, and
	relied on (``unrelied``); a Variation made from a priced Decision, that Decision's approval (decision_covers); and
	always while approvals are off (today's behaviour). Else why, as the record page shows it (P3-80, O4)."""
	if not cint(doc.get("client_approval_required")) or not cint(
			frappe.db.get_value("Construction Project", doc.project, "cc_portal_approvals")):
		return ""
	from construction_core.approvals import routes  # here: routes imports this module

	if doc.doctype == VO and decision_covers(doc):
		return routes.covered_reason(doc)  # P3-82 (§14.3 item 7): the Variation's own route still runs
	why = ""
	if latest and log.state_of(latest.name) == "Approved" and terms_hash(latest) == latest.terms_hash:
		why = unrelied(latest.name, doc.doctype == VO) or routes.waiting_reason(latest.name)  # §14.3 item 5
		if not why:
			return ""
	elif doc.doctype == VO and doc.get("decision_request"):
		why = unrelied(doc.decision_request, True)  # the approval it was made from, when that is why it does not cover
	from construction_core.approvals.api import approvers  # here: api imports this module

	return why or (_("Waiting for the client") if any(approvers(doc.project).values()) else _("No approver is set up"))


def unrelied(request: str, priced: bool) -> str:
	"""M9 (§3.7, §3.9, §4.5): why the team may not rely on a request's approval for a staff move, or "": a dispute open
	(or upheld), an answer given under a credential change found later, or a phone approval of a change in price or time
	(``priced``: a Variation, a priced Decision's), since Art. 1724 needs those in writing."""
	from construction_core.approvals import credentials, dispute, receipts  # here: each imports this module

	if dispute.disputed_open(request):
		return _("The client said this approval was not them. A manager resolves the dispute first.")
	if credentials.needs_reconfirmation(request):
		return _("Needs re-confirmation: someone else changed the client's account before this approval. Ask the "
			"client to approve it again.")
	e = receipts.answer_of(request)
	if priced and e and json.loads(e.canonical)["body"].get("method") == PHONE:
		return _("A phone approval does not cover a change in price or time. Record a paper or written approval, or ask "
			"the client to approve it in the portal.")
	return ""


def on_file_revised(project, old_sha: str) -> None:
	"""versions.revise (an upload, a restore, an Office save): the project's Open or Approved requests that froze these
	bytes, and whose record's terms now differ, are superseded (§3.10); an approval of a final record stays, and the
	change is recorded (L6). P3-82: a Decision the client approved, waiting for an after-client step, is as final."""
	from construction_core.approvals.routes import acknowledging  # here: routes imports this module
	for r in frappe.get_all(log.REQUEST, filters={"project": project, "status": ["in", ("Open", "Approved", log.INTERNAL)],
			"frozen_files": ["like", f"%{old_sha}%"]}, fields=FIELDS) if project else []:
		s = SUBJECTS.get(r.subject_doctype)
		if not s:
			continue
		if r.status == "Approved" and (frappe.db.get_value(r.subject_doctype, r.subject_name, s.state) in s.final
				or (r.subject_doctype == DECISION and acknowledging(r.subject_name))):
			_changed_after_decision(r)
		elif terms_hash(r) != r.terms_hash:
			supersede(r, "A file changed")


def _changed_after_decision(r) -> None:
	"""L6: an Approved request of a final record whose live terms differ from the last ones recorded (its latest
	changed_after_decision event's, else the approved ones) gets a changed_after_decision event: each change once, never
	again on a save that changes no term."""
	from construction_core.approvals.api import tell  # here: api imports this module
	last = frappe.get_all(log.EVENT, filters={"request": r.name, "kind": "changed_after_decision"}, pluck="canonical",
		order_by="seq desc", limit=1)
	live = terms_hash(r) or ""  # "": the terms cannot be built (a file to re-attach)
	if live != (json.loads(last[0])["body"]["terms_hash"] if last else r.terms_hash):
		log.append_event(r.project, "changed_after_decision", request=r.name, body={"terms_hash": live})
		tell(r, "changed")  # once per event: the approvers mailed, the managers on the bell


def on_variation_approved(vo) -> None:
	"""§3.1: another Variation approved on the same BOQ line changes this one's amounts (they follow on its next save), so
	its Open or Approved request is superseded."""
	mine = {_origin_of(d.boq_line) for d in vo.deltas if d.boq_line}
	for other in frappe.get_all(VO, filters={"project": vo.project, "stage": "Change Order Request",
			"name": ["!=", vo.name]}, pluck="name") if mine else []:
		lines = frappe.get_all("VO BOQ Delta", filters={"parenttype": VO, "parent": other, "boq_line": ["is", "set"]},
			pluck="boq_line")
		if mine & {_origin_of(line) for line in lines}:
			for r in requests_of(VO, other, status=["in", ("Open", "Approved", log.INTERNAL)]):
				supersede(r, "Another variation on the same BOQ line was approved")


# --- decisions (§3.3) and publishing (§3.11) --------------------------------------------------------------------------


def chosen(request: str) -> dict | None:
	"""An approved Decision request's chosen option as frozen: its approved event's "option" key (P3-78 writes it, L5)
	among the snapshot's options."""
	events = frappe.get_all(log.EVENT, filters={"request": request, "kind": "approved"}, pluck="canonical",
		order_by="seq desc", limit=1)
	key = json.loads(events[0])["body"].get("option") if events else None
	options = json.loads(frappe.db.get_value(log.REQUEST, request, "snapshot") or "{}").get("terms", {}).get("options")
	return next((o for o in options or [] if key and o.get("key") == key), None)


def decision_covers(vo) -> bool:
	"""§3.3: a Variation made from a priced Decision needs no request of its own while its total change and days equal the
	chosen option's frozen figures, in the frozen currency and VAT basis; the Decision's approval covers it."""
	r = frappe.db.get_value(log.REQUEST, vo.decision_request, ["project", "subject_doctype", "snapshot"], as_dict=True) \
		if vo.get("decision_request") else None
	option = chosen(vo.decision_request) if r and r.project == vo.project and r.subject_doctype == DECISION \
		and log.state_of(vo.decision_request) == "Approved" else None
	terms = json.loads(r.snapshot)["terms"] if option else {}
	return bool(option) and flt(vo.vo_delta_sum, PLACES) == flt(option["cost_difference"]) \
		and cint(vo.time_extension_days) == cint(option["time_difference"]) \
		and terms["currency"] == currency_of(vo.project) \
		and cint(terms["amounts_include_vat"]) == cint(vo.amounts_include_vat) \
		and not unrelied(vo.decision_request, True)


def approved_file_sha(document: str) -> str | None:
	"""The original SHA-256 a Document's latest approval froze for its file (§3.11), or None."""
	rows = requests_of(DOC, document, status="Approved")
	return (json.loads(rows[0].frozen_files).get("file") or {}).get("original_sha256") if rows else None
