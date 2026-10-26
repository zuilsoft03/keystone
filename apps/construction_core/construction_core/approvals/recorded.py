"""Approvals recorded by staff (approvals design §3.9; P3-78 M12; threat T21).

- ``record``: a manager (record_paper_approval) records an approval a named approver gave on paper, in a written
  message or by phone: when it was given (not the recording time), a proof file frozen after the client-file checks and
  the scan, and, for paper, who keeps the original and where. Only against an Open request whose terms are unchanged
  and whose record is still in its allowed state. It is a ``recorded`` chain event; the request stays Open.
- ``confirm``: another manager confirms it. When the recorder is the only manager who could, they confirm it themselves
  and the event says "same person" (§14.1). Every check runs again inside the lock (subject, project, request), since
  the approval happens here: then the ``approved`` event names its ``signer`` and its method, the receipts go out (the
  signer's with "This was not me", approvals.receipts) and the staff bell rings.
- A phone record never opens a priced gate (subjects.unrelied).
"""

import json

import frappe
from frappe import _
from frappe.utils import cstr, get_datetime, get_fullname, now_datetime

from construction_core.approvals import api, log, read, receipts, subjects
from construction_core.onboarding import invites

PTYPE = "record_paper_approval"
# each method's label, with the recorder and the day it was given (§3.9)
METHODS = {"paper": "Recorded by {0} from a signed paper copy on {1}",
	"written": "Recorded by {0} from a written message on {1}", "phone": "Verbal instruction recorded by {0} on {1}"}
COPIED = ("method", "label", "signer", "signer_name", "given_at", "proof", "proof_name", "original", "terms_hash")


def _staff(request):
	r = read.readable(request)
	if not r:
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.has_permission(api.PROJECT, PTYPE, doc=r.project, throw=True)
	return r


def _open(request):
	"""Inside the lock, taken by log.terms_agree in the order subject, project, request (D-459): the request Open, its
	terms unchanged (the four-hash check) and its record in its allowed state (T19, T21); else a plain refusal."""
	terms_ok = log.terms_agree(request, log.prehash(request))
	row = frappe._dict(log.lock(frappe.db.get_value(log.REQUEST, request, "project"), request))
	if log.state_of(request) != "Open":
		frappe.throw(_("Only a request still waiting for the client can be approved. This one is {0}.").format(
			_(row.status)))
	if not terms_ok or not subjects.allowed(frappe.get_doc(row.subject_doctype, row.subject_name)):
		frappe.throw(_("The record changed or moved on since it was sent. Send it to the client again first."))
	return row


def _confirmers(project) -> list[str]:
	"""The managers who could confirm a recorded approval: the project's enabled managers who may record one."""
	return [u for u in invites._managers(project) if frappe.has_permission(api.PROJECT, PTYPE, doc=project, user=u)]


@frappe.whitelist(methods=["POST"])
def record(request: str, method: str, member: str, given_at: str, proof_file: str, original: str | None = None,
		option: str | None = None) -> dict:
	"""Record an approval given outside the portal (§3.9). ``member``: the approver's Project Member row; ``given_at``:
	when they gave it, after the request was sent and not in the future; ``option``: a Decision's chosen option key.
	Answers {recorded, self_confirm}: whether the recorder confirms it themselves (no other manager could)."""
	r = _staff(request)
	if method not in METHODS:
		frappe.throw(_("Say how the client gave it: on paper, in a written message or by phone."))
	try:
		at = get_datetime(given_at) if isinstance(given_at, str) and given_at else None
		if at and not get_datetime(r.creation) <= at <= now_datetime():  # the site's local time; an aware one fails here
			at = None
	except Exception:
		at = None
	if not at:
		frappe.throw(_("Say when the client gave it: after the request was sent, and not in the future."))
	original = cstr(original).strip()[:api.NOTE_MAX]
	if method == "paper" and not original:
		frappe.throw(_("Say who keeps the signed paper and where."))
	proof, proof_name = api._freeze_file(r.project, proof_file, checked=True)  # before the lock: the scan takes time

	def _record() -> dict:
		row = _open(r.name)
		project = frappe.get_doc(api.PROJECT, row.project)
		signer = api._contact_row(project, member).user
		if not api.approvers(row.project).get(signer):
			frappe.throw(_("Only a confirmed approver of this project can give an approval."), frappe.PermissionError)
		chosen = None
		if row.subject_doctype == subjects.DECISION:  # T11: one of the frozen options
			chosen = next((o for o in json.loads(row.snapshot)["terms"].get("options") or [] if o["key"] == option), None)
			if not chosen:
				frappe.throw(_("Choose the option the client chose."))
		body = {"method": method, "label": METHODS[method].format(get_fullname(frappe.session.user), f"{at:%d %b %Y}"),
			"signer": signer, "signer_name": get_fullname(signer), "given_at": at, "proof": proof,
			"proof_name": proof_name, "original": original, "terms_hash": row.terms_hash,
			**({"option": chosen["key"]} if chosen else {})}
		name = log.append_event(row.project, "recorded", request=row.name, body=body)
		return {"recorded": name, "self_confirm": not [u for u in _confirmers(project) if u != frappe.session.user]}

	return log.retry_once(_record)


@frappe.whitelist(methods=["POST"])
def confirm(request: str, recorded: str) -> dict:
	"""Confirm a recorded approval (§3.9): the request's latest ``recorded`` event, by another manager, or by its
	recorder when no other manager could ("same person"). The request is then Approved."""
	r = _staff(request)

	def _confirm() -> dict:
		row = _open(r.name)
		latest = frappe.db.sql("""select name, actor, canonical from `tabApproval Event` where request = %s
			and kind = 'recorded' order by seq desc limit 1 for update""", (row.name,), as_dict=True)
		if not latest or latest[0].name != recorded:
			frappe.throw(_("This is not the latest approval recorded for this request. Reload the page and check it."))
		body, recorder, me = json.loads(latest[0].canonical)["body"], latest[0].actor, frappe.session.user
		same = recorder == me
		if same and [u for u in _confirmers(frappe.get_doc(api.PROJECT, row.project)) if u != me]:
			frappe.throw(_("Another manager of this project confirms an approval you recorded."), frappe.PermissionError)
		if not api.approvers(row.project).get(body["signer"]):
			frappe.throw(_("{0} is no longer a confirmed approver of this project.").format(body["signer_name"]))
		name = log.append_event(row.project, "approved", request=row.name, body={
			**{k: body[k] for k in COPIED}, **({"option": body["option"]} if body.get("option") else {}),
			"recorded": latest[0].name, "recorded_by": recorder, "confirmed_by": me, "same_person": "1" if same else "0"})
		receipts.queue(name)  # after the commit: the signer's receipt carries "This was not me"
		from construction_core.approvals import routes  # here: routes imports api, which imports a lot

		routes.client_approved(row, frappe.get_doc(row.subject_doctype, row.subject_name))  # as decide does (P3-82)
		api.answered(row, "approved", body["signer"])
		return {"state": "approved", "request": row.name, "event": name, "same_person": same}

	return log.retry_once(_confirm)
