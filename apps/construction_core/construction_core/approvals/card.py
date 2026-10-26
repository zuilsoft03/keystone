"""The approval card (approvals design §3.12, §7; P3-78): one live card per request in the Client room, and a line in the
Team room when a client answers. Both are System messages whose Discuss Pointer targets the request, so the approval
part (discuss/parts/approval.py) draws them per viewer at read time and respond() drops one the viewer may not read
(T30). Nothing of the request is copied into the message.

- **Every state change is an Approval Event** (approvals.log), so one hook on its insert (``on_event``) follows the chain:
  ``requested`` posts the card, each other change tells the card's readers by ids (``live.message_changed``), and a
  client's own answer adds the Team line, authored by the requester. The work is a job queued after the commit (as the
  receipts are), so a failed card never takes an answer back, and it is one transaction: no card without its pointer.
  It decides from the event's kind, never the request's status, which a synchronous test run has not saved yet.
- **The Client card** is posted only when every client of the room may read the request now (its own read rule and the
  approvals section), and not into a Locked room. A request opened while the section was off has no card.
- **The Team line** is drawn from the request's answer, so it stays true after a later replace or void. P3-82: an
  internal step's line (approvals.routes posts one per step) is drawn from the step event it was posted after, so each
  line keeps its own step. The Client card never shows a step.
"""

import json

import frappe
from frappe import _
from frappe.utils import convert_utc_to_system_timezone, get_datetime, get_fullname

from construction_core.approvals import log, read
from construction_core.discuss import live, rooms, send
from construction_core.permissions import CLIENT_SECTION

CHANGES = ("approved", "returned", "superseded", "voided", "disputed", "dispute_resolved")  # what a card shows
ANSWERS = ("approved", "returned")
STEPS = ("internal_approved", "internal_returned", "internal_acknowledged")  # P3-82: Team lines only
FIELDS = ("name", "project", "status", "decider_party", "subject_doctype", "subject_name", "subject_title", "due_date",
	"successor")


# --- following the chain ------------------------------------------------------------------------------------------


def on_event(doc, method=None):
	"""Approval Event after_insert: the card follows the chain, in a job once this transaction commits (as the receipts
	do): a rollback drops it and an outage of the job queue never fails an answer."""
	if not (doc.request and doc.kind in ("requested", *CHANGES)):
		return
	if frappe.flags.cc_events_sync:  # tests only (core.events): in-process
		return job(doc.name)
	frappe.db.after_commit.add(lambda: _enqueue(doc.name))


def _enqueue(event: str) -> None:
	try:
		frappe.enqueue(f"{__name__}._job", queue="short", approval_event=event)
	except Exception as e:  # not log_error: an outage would flood the log once per event; the card is a convenience
		frappe.logger("construction_core").warning(f"an approval card could not be queued: {type(e).__name__} {event}")


def _job(approval_event: str) -> None:
	frappe.set_user("Administrator")  # the site posts it, authored by the requester, whoever answered
	job(approval_event)


def job(approval_event: str) -> None:
	"""The card or the line this chain event calls for."""
	e = frappe.db.get_value(log.EVENT, approval_event, ["request", "kind", "canonical"], as_dict=True)
	r = frappe.db.get_value(log.REQUEST, e.request, [*FIELDS, "requester"], as_dict=True) if e else None
	if not r:
		return
	if e.kind == "requested":
		return post_card(r)
	if e.kind in ANSWERS and "answer_id" in json.loads(e.canonical)["body"]:  # a client's own answer, not a record by staff
		_post(r, "Internal")
	_changed(r)


def post_card(r) -> str | None:
	"""The request's card in its project's Client room, once; None when the room's clients may not read it now."""
	from construction_core.records.resolve import audience_reads

	if r.decider_party != "client" or not audience_reads("Client", frappe._dict(r, doctype=log.REQUEST)):
		return None
	if frappe.db.exists("Discuss Pointer", {"target_type": log.REQUEST, "target_name": r.name, "audience": "Client"}):
		return None
	return _post(r, "Client")


def _post(r, audience: str) -> str | None:
	thread = rooms.room(r.project, audience)
	if frappe.db.get_value("Discuss Thread", thread, "status") == "Locked":
		return None
	return send.post_system(thread, r.requester, targets=[(log.REQUEST, r.name)])


def _changed(r) -> None:
	"""Tell the readers of each message that points at the request (ids only)."""
	for m in frappe.db.sql("""select m.name, m.thread, m.project, m.audience, m.staff_only from `tabDiscuss Pointer` p
			join `tabDiscuss Message` m on m.name = p.message where p.target_type = %s and p.target_name = %s""",
			(log.REQUEST, r.name), as_dict=True):
		live.message_changed(m, "approval")


# --- what a viewer sees -------------------------------------------------------------------------------------------


def chain(names: list) -> dict:
	"""{request: {"answer": the approved or returned event or None, "dispute": "" | open | upheld | ..., "reason": why it
	was voided}} from the chain, in one query for any number of requests."""
	from construction_core.approvals import dispute  # here: dispute imports api, which imports log

	out = {n: {"answer": None, "disputes": [], "reason": "", "steps": []} for n in names}
	if not out:
		return {}
	for kind, request, actor, at, text in frappe.db.sql("""select kind, request, actor, at_utc, canonical
			from `tabApproval Event` where request in %s and kind in ('approved', 'returned', 'disputed',
			'dispute_resolved', 'voided', 'internal_approved', 'internal_returned', 'internal_acknowledged')
			order by seq""", (tuple(out),)):
		body = json.loads(text)["body"]
		if kind in ANSWERS:
			out[request]["answer"] = frappe._dict(kind=kind, actor=actor, at=at, body=body)
		elif kind in STEPS:
			out[request]["steps"].append(frappe._dict(kind=kind, actor=actor, at=at, body=body))
		elif kind == "voided":
			out[request]["reason"] = body.get("reason") or ""
		else:
			out[request]["disputes"].append((kind, body))
	return {n: {"answer": c["answer"], "dispute": dispute._state(c["disputes"]), "reason": c["reason"],
		"steps": c["steps"]} for n, c in out.items()}


def state(status: str, known: dict) -> str:
	"""waiting, approved, returned, recorded (approved by staff's record), disputed, replaced, voided, internal_review
	(P3-82, staff only) or draft."""
	if status == "Open":
		return "waiting"
	if status == log.INTERNAL:
		return "internal_review"
	if status in ("Approved", "Returned"):
		answer = known["answer"]
		if known["dispute"] in ("open", "upheld"):
			return "disputed"
		return "recorded" if status == "Approved" and answer and answer.body.get("method") else status.lower()
	return {"Superseded": "replaced", "Voided": "voided"}.get(status, "draft")


def item(r, known: dict, audience: str, posted=None) -> dict:
	"""One card as a viewer reads it (the request's read rule decided before this): its state in words, who answered and
	when. Never the signature, the evidence or the receipt (T25). In the Team room, the line tells the answer, or the
	internal step it was ``posted`` (the message's creation) after."""
	s, answer = state(r.status, known), known["answer"]
	step = _step_of(known, posted) if audience == "Internal" else None
	if step:
		by = get_fullname(step.actor)
		words = {"internal_approved": _("{0} approved {1} · {2}"), "internal_returned": _("{0} returned {1} · {2}"),
			"internal_acknowledged": _("{0} noted {1} · {2}")}[step.kind]
		text = words.format(by, step.body.get("name") or "", convert_utc_to_system_timezone(step.at).strftime("%H:%M"))
		if step.body.get("same_person") == "1":
			text += " · " + _("same person")
		return {"_ref": (log.REQUEST, r.name), "type": "approval", "request": r.name, "state": s, "text": text,
			"title": r.subject_title or r.subject_name, "reference": r.subject_name, "kind": r.subject_doctype, "by": by,
			"at": f"{step.at}Z", "due_date": str(r.due_date or ""), "route": {"project": r.project, "request": r.name,
				"section": CLIENT_SECTION.get(r.subject_doctype)}}
	by = at = clock = None
	if answer:
		by = answer.body.get("signer_name") or (answer.body.get("who") or {}).get("full_name") or get_fullname(answer.actor)
		at, clock = f"{answer.at}Z", convert_utc_to_system_timezone(answer.at).strftime("%H:%M")
	title = r.subject_title or r.subject_name
	return {"_ref": (log.REQUEST, r.name), "type": "approval", "request": r.name, "state": s,
		"text": _text(s, answer, audience, by, clock, title, known["reason"], r.successor),
		"title": title, "reference": r.subject_name,
		"kind": r.subject_doctype, "by": by, "at": at, "due_date": str(r.due_date or ""),
		# P3-79 (N3): ids only. The item exists only for a viewer who reads the request, so this is the route to its sheet
		# (the portal's ?tab=approvals&request=, as the request mail's link); the screen picks the target by who views. A staff
		# viewer opens the subject record in its section, which the screen cannot name (no section: no page for it yet).
		"route": {"project": r.project, "request": r.name, "section": CLIENT_SECTION.get(r.subject_doctype)}}


def _step_of(known, posted):
	"""The step event a Team line was posted after, when that is the request's latest event at the line's time."""
	if not posted or not known.get("steps"):
		return None
	at = get_datetime(posted)
	seen = [e for e in [*known["steps"], *([known["answer"]] if known["answer"] else [])]
		if convert_utc_to_system_timezone(e.at).replace(tzinfo=None) <= at]
	latest = max(seen, key=lambda e: e.at, default=None)
	return latest if latest is not None and latest.kind in STEPS else None


def _text(s, answer, audience, by, clock, title, reason, successor) -> str:
	from construction_core.approvals.api import NOTHING_NEEDED  # here: api imports a lot

	if audience == "Internal" and answer and s != "disputed":
		line = _("{0} approved {1} · {2}") if answer.kind == "approved" else _("{0} returned {1} · {2}")
		return line.format(by, title, clock)
	if s in ("approved", "returned"):
		return (_("Approved by {0} · {1}") if s == "approved" else _("Returned by {0} · {1}")).format(by, clock)
	if s == "replaced":  # what to do, as the mail says (§3.10): a new request carries its own
		while successor and not read.asked(successor):  # an internal one the client never saw: the one sent on from it
			successor = frappe.db.get_value(log.REQUEST, successor, "successor")
		if successor:
			return _("Replaced by a newer request. Please answer that one instead.")
		return _("Replaced by a newer version. {0}").format(_(NOTHING_NEEDED))
	if s == "voided":
		return _("Voided by the team: {0}. {1}").format(reason or _("no reason given"), _(NOTHING_NEEDED))
	return {"waiting": _("Waiting for approval"), "draft": _("Not sent yet"), "internal_review": _("In internal review"),
		"disputed": _("Disputed. The team does not rely on this approval until it is resolved."),
		"recorded": _("Recorded by staff: approved by {0}").format(by)}[s]
