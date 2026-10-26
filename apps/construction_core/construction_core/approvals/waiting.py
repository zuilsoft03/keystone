"""The client portal's approvals (P3-79; design §3.12): what the Approvals tab, the Home card and the tab's badge draw.

``rows(project, user)`` is the one source for all three: the requests ``user`` may read (the request's own read rule,
approvals.read, through get_list as that user), each as the read-only sheet shows it, less an Open request for anyone who
is not a confirmed approver (N11: a contact waiting for the second staff confirmation has nothing to answer, so no
badge; they reach a request's read-only sheet from a link or the chat card). Nothing here is evidence: no signature,
address, device, location or hash leaves, and a returned answer's reason only to the person who gave it.
"""

import json

import frappe
from frappe.utils import get_fullname

from construction_core.approvals import card
from construction_core.approvals.api import approvers, confirmed_projects

STATES = ("Open", "Approved", "Returned")
LIMIT = 100  # newest first: every Open one is among them in any real project
FIELDS = ["name", "status", "subject_doctype", "subject_name", "subject_title", "due_date", "note", "snapshot",
	"frozen_files"]
# the terms the tab draws; the sheet (answer.sheet) gives a reader all of them
TERMS = ("title", "total", "days", "currency", "revision", "number", "options", "recommended")


def rows(project: str, user: str) -> list[dict]:
	names = frappe.get_list("Approval Request", filters={"project": project, "status": ["in", STATES]}, pluck="name",
		order_by="modified desc", limit=LIMIT, user=user)
	if not names:
		return []
	confirmed = project in confirmed_projects(user, [project])
	known = card.chain(names)
	people = [get_fullname(u) for u, ok in approvers(project).items() if ok]
	out = []
	for r in frappe.get_all("Approval Request", filters={"name": ["in", names]}, fields=FIELDS, order_by="modified desc"):
		if r.status == "Open" and not confirmed:
			continue
		terms = json.loads(r.snapshot)["terms"]
		answer = known[r.name]["answer"]
		body = answer.body if answer else {}
		decider = body.get("signer") or (body.get("who") or {}).get("user") or (answer.actor if answer else "")
		mine = bool(answer) and decider == user
		out.append({"name": r.name, "kind": r.subject_doctype, "status": r.status, "state": card.state(r.status, known[r.name]),
			"reference": terms.get("number") or r.subject_name, "title": r.subject_title or terms.get("title") or "",
			"due_date": str(r.due_date or ""), "note": r.note or "", "terms": {k: terms[k] for k in TERMS if k in terms},
			"files": [{**{k: e[k] for k in ("key", "name", "type", "size", "rev")},
				"url": f"/api/method/construction_core.approvals.file?request={r.name}&key={e['key']}"}
				for e in json.loads(r.frozen_files or "{}").values()],
			"approvers": people if r.status == "Open" else [], "mine": mine,
			"by": (body.get("signer_name") or (body.get("who") or {}).get("full_name") or get_fullname(answer.actor)) if answer else "",
			"at": f"{answer.at}Z" if answer else "", "reason": (body.get("reason") or "") if mine else ""})
	return out
