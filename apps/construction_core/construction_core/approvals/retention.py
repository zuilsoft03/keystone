"""Retention of approval evidence (design §4.1, §4.8; P3-81): the daily clearing and the legal hold.

- **Location** rests on consent, so an answer's location is emptied at project completion (``log.clear_location``) with
  a ``location_cleared`` event, unless a legal hold is on its request.
- **Retention end**, per request: ``retention_end`` when the request carries one, else the project's completion plus its
  class's years. Past it, each answer's personal detail row goes (``log.clear_detail``) and its signature picture is
  removed from the frozen store after the commit, with one ``retention_cleared`` event per answer. The answer event and
  its hashes stay. A legal hold stops it; a request whose project has not completed never clears.
- **Legal hold**: a request's hold is its last ``legal_hold`` event's ``on`` (read from the chain, no column), set and
  lifted by a System Manager from the console, like privacy.erase.

``run`` is called by digest.daily (the scheduler's Administrator, as approvals.api.remind runs); one request that fails
never stops the others, and each request's clearing and its events are one transaction (a savepoint, then a commit),
so no lock is held across requests and a later failure takes back nothing already cleared.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_years, cstr, getdate, nowdate

from construction_core.approvals import frozen, log

PROJECT = "Construction Project"
# §4.8 (Arts. 1144, 1723): the firm's lawyer sets the final periods
YEARS = {"Standard": 10, "Drawings and structural": 25}
LONGEST = max(YEARS.values())  # an empty or unknown class: clearing too early cannot be undone
REASON_MAX = 500


def run() -> dict:
	"""Daily, from digest.daily: locations cleared at completion and evidence cleared at retention end. Returns how many
	answers had each cleared."""
	frappe.only_for("System Manager")
	done = {"location_cleared": 0, "retention_cleared": 0}
	today_ = getdate(nowdate())
	for project in frappe.get_all(PROJECT, filters={"status": "Completed"}, pluck="name"):
		completed = completed_on(project)
		if not completed:
			continue  # shortcut: no completion recorded (status set without a Version): nothing clears until one is
		for name in frappe.get_all(log.REQUEST, filters={"project": project}, pluck="name", order_by="creation asc"):
			point = "cc_approval_retention_" + frappe.generate_hash(length=8)
			frappe.db.savepoint(point)
			try:
				kind, count, signatures = _clear(project, name, completed, today_)
			except Exception:
				frappe.db.rollback(save_point=point)
				frappe.log_error(title="construction_core: approval retention failed", reference_doctype=log.REQUEST,
					reference_name=name)
				continue
			frappe.db.release_savepoint(point)
			for sha in signatures:  # a file is never rolled back: removed only once the clearing is committed
				frappe.db.after_commit.add(lambda sha=sha: frozen.remove(sha))
			frappe.db.commit()
			if kind:
				done[kind] += count
	return done


def completed_on(project: str):
	"""The date the project last moved to Completed, from its Version history (track_changes), or None.
	shortcut: final payment and the last written demand are not in the data; the legal hold covers them until then."""
	for v in frappe.get_all("Version", filters={"ref_doctype": PROJECT, "docname": project},
			fields=["data", "creation"], order_by="creation desc"):
		change = next((c for c in (json.loads(v.data or "{}").get("changed") or []) if c and c[0] == "status"), None)
		if change:
			return getdate(v.creation) if change[2] == "Completed" else None
	return None


def _clear(project: str, request: str, completed, today_) -> tuple[str, int, list[str]]:
	"""One request, under the lock (the project row, then the request row): what it cleared, for how many answers, and
	at retention end the signature pictures to remove after the commit."""
	r = log.lock(project, request)
	if held(request):  # read inside the lock: a hold set at this moment is seen
		return "", 0, []
	answers = frappe.db.sql("""select e.name as event, e.canonical, d.name as detail, d.location
		from `tabApproval Event` e join `tabApproval Evidence Detail` d on d.event = e.name
		where e.request = %s order by e.seq asc""", (request,), as_dict=True)
	if not answers:
		return "", 0, []
	if today_ > end_of(r, completed):
		signatures = []
		for a in answers:
			sha = cstr((json.loads(a.canonical)["body"].get("signature") or {}).get("file"))
			log.clear_detail(a.detail)
			log.append_event(project, "retention_cleared", request=request,
				body={"event": a.event, "detail": a.detail, "signature": sha})
			signatures.append(sha)
		return "retention_cleared", len(answers), [s for s in signatures if s]
	located = [a for a in answers if a.location]
	for a in located:
		log.clear_location(a.detail)
		log.append_event(project, "location_cleared", request=request, body={"event": a.event, "detail": a.detail})
	return "location_cleared", len(located), []


def end_of(r, completed):
	"""A request's retention end: its ``retention_end``, else its project's completion plus its class's years."""
	return getdate(r.retention_end) if r.retention_end else add_years(completed, YEARS.get(r.retention_class, LONGEST))


def completions(project: str) -> list:
	"""Every date the project moved to Completed (verify asks whether a clearing came after one)."""
	out = []
	for v in frappe.get_all("Version", filters={"ref_doctype": PROJECT, "docname": project}, fields=["data", "creation"]):
		if any(c and c[0] == "status" and c[2] == "Completed" for c in json.loads(v.data or "{}").get("changed") or []):
			out.append(getdate(v.creation))
	return sorted(out)


def held(request: str) -> bool:
	rows = frappe.db.sql("""select canonical from `tabApproval Event` where request = %s and kind = 'legal_hold'
		order by seq desc limit 1 lock in share mode""", (request,))  # the latest committed hold, not the snapshot's
	return bool(rows) and json.loads(rows[0][0])["body"].get("on") == "1"


def legal_hold(request: str, on, reason: str) -> str:
	"""Set (``on`` "1") or lift ("0") a request's legal hold, with the reason. System Manager only; not whitelisted (the
	console, RUNBOOK §11). Returns the event's name."""
	frappe.only_for("System Manager")
	on = {"1": "1", "0": "0", 1: "1", 0: "0"}.get(on)
	reason = " ".join(cstr(reason).split())[:REASON_MAX]
	if not on or not reason:
		frappe.throw(_("Say whether the hold is on (1) or off (0), and why"))
	project = frappe.db.get_value(log.REQUEST, request, "project") if isinstance(request, str) else None
	if not project:
		raise frappe.DoesNotExistError(_("Not found"))
	return log.append_event(project, "legal_hold", request=request, body={"on": on, "reason": reason})
