"""Internal approval steps (approvals design §14; P3-82): what a firm configures around the client step, and how a
request runs through it. The client step itself stays in code (§14.1): no route can remove it, move it or stand in for
it, and an internal step never counts as a client's answer.

- **Routes** (§14.2): one optional Approval Route per record kind, written by a System Manager. Each save is checked
  (``check_route``: every step names someone who can exist, never a client), appends an Approval Route Version (its
  canonical text and SHA-256, the author and the time, append-only under the ledger's claim) and rings every
  Construction Manager (``route_saved``). No route, or none of its steps applying: today's behaviour.
- **Freezing** (§14.2): ``resolve`` reads the latest version and resolves each step for this project and these terms
  (who is eligible now, whether its condition applies); request() writes it as the request's ``route_frozen`` event.
  A later route edit never reaches a request under way. Routes run only where the record needs client approval (Q6).
- **Running** (§14.3): a request whose before-client steps apply starts In internal review (staff-only, never a
  client's: approvals.read). Steps run in their order; each binds to the request's terms_hash, and a change of the
  terms supersedes the request (approvals.subjects), so its steps start over with a new send. A Return goes back to the
  sender (edit and send again, or void). The last before-client step sends a new Open request in its place, with the
  same frozen terms and route (``release``): the client's card, email, due date and reminders start then (Q5), and the
  request in review is superseded by it, never having reached the client.
- **After the client** (§14.1, §14.3 item 5): acknowledgements only, once the client approved; the gate
  (subjects.gate_reason, ``waiting_reason``) waits for them, and a Decision is Decided only after them (so Make the
  variation waits too). A Variation made from a decision (subjects.decision_covers) still runs its own route
  (``covered_reason``): sent, it runs every step In internal review and never goes to the client.
- **Separation of duties** (§14.1, ``_same_person``): the sender does not do a step and one person does not fill two
  steps while anyone else is eligible; otherwise it is allowed and recorded as "same person".
- Each step is a staff-only chain event (``internal_approved``, ``internal_returned``, ``internal_acknowledged``) and a
  Team room System line (approvals.card draws it). Each step's people get a bell when it waits on them; one past its
  due time reminds them and tells the sender (``remind``, daily); staff Nudge (api.nudge).
"""

import json
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import (add_days, cint, convert_utc_to_system_timezone, cstr, date_diff, flt, fmt_money, get_fullname,
	getdate, nowdate)

from construction_core.approvals import canonical, card, log, read, subjects
from construction_core.notifications import ROUTE_CHANGED, STEP_OVERDUE, STEP_RETURNED, STEP_WAITING, key, notify
from construction_core.permissions import is_client

ROUTE, REQUEST, PROJECT = "Approval Route", log.REQUEST, "Construction Project"
INTERNAL = log.INTERNAL
KINDS = (subjects.VO, subjects.SUB, subjects.DOC, subjects.DECISION)
POSITIONS = {"Before the client": "before", "After the client": "after"}
WHO = {"Project role": "project_role", "Staff role": "staff_role", "People": "people"}
RULES = {"Any one": "any", "All": "all"}
CONDITIONS = {"Always": "always", "Cost above": "cost", "Days above": "days"}
PROJECT_ROLES = ("Project Manager", "Architect", "Engineer", "Site", "Consultant")  # Project Member's, never "Client"
STAFF_ROLES = ("Construction Manager", "Construction Staff")
DONE = ("internal_approved", "internal_acknowledged")
STEPS = (*DONE, "internal_returned")
REASON_MAX = 1000
LIMIT = 30  # steps per route


# --- routes (§14.2) -----------------------------------------------------------------------------------------------


def _people(value) -> list[str]:
	lines = value if isinstance(value, list) else cstr(value).replace(",", "\n").splitlines()
	return sorted({cstr(u).strip() for u in lines if cstr(u).strip()})


def steps_of(route) -> list[dict]:
	"""A route's steps as its version's canonical text holds them, in order."""
	out = []
	for n, s in enumerate(route.steps, start=1):
		who, condition = WHO.get(s.who), CONDITIONS.get(s.condition)
		out.append({"no": str(n), "name": cstr(s.step_name).strip(), "position": POSITIONS.get(s.position),
			"who": who, "role": cstr(s.project_role if who == "project_role" else s.staff_role if who == "staff_role"
				else ""), "people": _people(s.people) if who == "people" else [], "rule": RULES.get(s.rule),
			"condition": condition, "above": Decimal(str(flt(s.amount))) if condition == "cost" else
				cint(s.days) if condition == "days" else 0, "due_days": cint(s.due_days)})
	return out


def _staff_account(user) -> bool:
	row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True) if user else None
	return bool(row and row.enabled and row.user_type == "System User" and not is_client(user))


def check_route(route) -> None:
	"""Approval Route validate: each step names someone who can exist, never a client (§14.2)."""
	if len(route.steps) > LIMIT:
		frappe.throw(_("A route has at most {0} steps").format(LIMIT))
	for s in steps_of(route):
		label = _("Step {0}").format(s["no"])
		if not s["name"] or len(s["name"]) > 140:
			frappe.throw(_("{0}: give the step a name").format(label))
		if None in (s["position"], s["who"], s["rule"], s["condition"]):
			frappe.throw(_("{0}: choose its position, who, rule and condition").format(label))
		if s["who"] == "project_role" and s["role"] not in PROJECT_ROLES:
			frappe.throw(_("{0}: choose a project role").format(label))
		if s["who"] == "staff_role" and (s["role"] not in STAFF_ROLES or not frappe.db.exists("Role", s["role"])):
			frappe.throw(_("{0}: choose a staff role").format(label))
		if s["who"] == "people" and (not s["people"] or not all(_staff_account(u) for u in s["people"])):
			frappe.throw(_("{0}: name one or more staff accounts that are enabled").format(label))
		if s["condition"] != "always" and not s["above"] > 0:
			frappe.throw(_("{0}: give the amount or the days the condition is above").format(label))
		if not 1 <= s["due_days"] <= 30:
			frappe.throw(_("{0}: the due time is 1 to 30 working days").format(label))


def route_text(route) -> str:
	return canonical.text({"route": route.name, "steps": steps_of(route)}, subjects.PLACES)


def latest_version(kind: str):
	rows = frappe.get_all(log.ROUTE_VERSION, filters={"route": kind}, fields=["name", "sha256", "canonical", "author",
		"at_utc"], order_by="at_utc desc, creation desc", limit=1)
	return rows[0] if rows else None


def route_saved(route) -> None:
	"""Approval Route on_update: a new version when the steps changed, and every Construction Manager's bell."""
	text = route_text(route)
	last = latest_version(route.name)
	if last and last.sha256 == canonical.sha256(text):
		return
	log._write(frappe.get_doc({"doctype": log.ROUTE_VERSION, "route": route.name, "author": frappe.session.user,
		"at_utc": log._now().replace(tzinfo=None), "sha256": canonical.sha256(text), "canonical": text}), "insert")
	managers = frappe.get_all("Has Role", filters={"parenttype": "User", "role": "Construction Manager"}, pluck="parent")
	notify(managers, ROUTE_CHANGED, route)


# --- resolving and freezing (§14.2) -------------------------------------------------------------------------------


def needs_route(doc) -> bool:
	"""Q6: routes run only where the record needs client approval (a Decision always does)."""
	return doc.doctype == subjects.DECISION or bool(cint(doc.get("client_approval_required")))


def _figures(doctype, terms, chosen=None) -> tuple[Decimal, int]:
	"""(cost, days) a condition reads: a Variation's total change; a Decision's chosen option, or before the client its
	largest; nothing for a submittal or a document."""
	def pair(cost, days):
		return abs(Decimal(str(cost or 0))), abs(int(str(days or 0)))

	if chosen:
		return pair(chosen["cost_difference"], chosen["time_difference"])
	if doctype == subjects.DECISION:
		options = [pair(o["cost_difference"], o["time_difference"]) for o in terms.get("options") or []]
		return max((c for c, _d in options), default=Decimal(0)), max((d for _c, d in options), default=0)
	if doctype == subjects.VO:
		return pair(terms.get("total"), terms.get("days"))
	return Decimal(0), 0


def _applies(step, figures) -> bool:
	if step["condition"] == "cost":
		return figures[0] > Decimal(step["above"])
	if step["condition"] == "days":
		return figures[1] > int(step["above"])
	return True


def people_of(project: str, step: dict) -> list[str]:
	"""Who on this project may do the step now: the project's staff (enabled, reading its requests) with the step's
	project role or staff role, or named in it. Never a client."""
	from construction_core.discuss.live import staff_members

	staff = [u for u in staff_members(project) if _staff_account(u)
		and frappe.has_permission(REQUEST, "read", user=u, throw=False)]
	if step["who"] == "project_role":
		roled = set(frappe.get_all("Project Member", filters={"parenttype": PROJECT, "parent": project,
			"cc_workspace_role": step["role"]}, pluck="user"))
		return sorted(u for u in staff if u in roled)
	if step["who"] == "staff_role":
		return sorted(u for u in staff if step["role"] in frappe.get_roles(u))
	return sorted(u for u in staff if u in step["people"])


def resolve(doc, terms, covered: str = "") -> dict | None:
	"""The route a request on ``doc`` with ``terms`` freezes, or None: its version, and each step with who is eligible
	now and whether it applies ("1"/"0"; "" for a Decision's after-client step, decided by the chosen option)."""
	if not needs_route(doc):
		return None
	version = latest_version(doc.doctype)
	steps = json.loads(version.canonical)["steps"] if version else []
	if not steps:
		return None
	figures = _figures(doc.doctype, terms)
	out = []
	for s in steps:
		later = s["position"] == "after" and doc.doctype == subjects.DECISION
		out.append({**s, "eligible": people_of(doc.project, s), "applies": "" if later else
			"1" if _applies(s, figures) else "0"})
	return {"route": doc.doctype, "version": version.name, "version_sha256": version.sha256, "covered_by": covered,
		"steps": out}


def starts_internal(route) -> bool:
	"""A request starts In internal review when a before-client step applies, or, for a Variation its decision covers,
	any step does (it never goes to the client)."""
	return bool(route) and any(s["applies"] == "1" and (s["position"] == "before" or route["covered_by"])
		for s in route["steps"])


def terms_for(doc) -> dict:
	"""The record's live terms for a condition and the Ask sheet; no file is hashed (the request hashes them)."""
	return log.terms_of(doc.doctype, doc.name, lambda _file: "")


# --- a request's progress ---------------------------------------------------------------------------------------------


def _frozen(request) -> dict | None:
	rows = frappe.get_all(log.EVENT, filters={"request": request, "kind": "route_frozen"}, pluck="canonical",
		order_by="seq desc", limit=1) if request else []
	return json.loads(rows[0])["body"] if rows else None


def _events(request) -> list:
	return [frappe._dict(e, body=json.loads(e.canonical)["body"]) for e in frappe.get_all(log.EVENT,
		filters={"request": request, "kind": ["in", STEPS]}, fields=["name", "kind", "actor", "at_utc", "canonical"],
		order_by="seq asc")] if request else []


def progress(request: str):
	"""The request's route as it runs: {body, status, steps, current, returned, events, complete}, or None without a
	route. A request sent on from internal review (``from``) carries its predecessor's before-client steps as done."""
	body = _frozen(request)
	if not body:
		return None
	r = frappe.db.get_value(REQUEST, request, ["name", "status", "requester", "subject_doctype"], as_dict=True)
	events = _events(body.get("from")) + _events(request)
	chosen = subjects.chosen(request) if r.status == "Approved" and r.subject_doctype == subjects.DECISION else None
	steps = []
	for s in body["steps"]:
		applies = s["applies"] if s["applies"] else ("1" if chosen and _applies(s, _figures(r.subject_doctype, {},
			chosen)) else "0" if chosen else "")
		by = [e for e in events if e.body.get("step") == s["no"] and e.kind in DONE]
		done = bool(by) if s["rule"] == "any" else bool(s["eligible"]) and set(s["eligible"]) <= {e.actor for e in by}
		steps.append(frappe._dict(s, applies=applies, by=by, done=done))
	returned = next((e for e in reversed(events) if e.kind == "internal_returned"), None) \
		if r.status == INTERNAL else None
	if r.status == INTERNAL and not returned:
		turn = [s for s in steps if s.position == "before" or body.get("covered_by")]
	elif r.status == "Approved":
		turn = [s for s in steps if s.position == "after"]
	else:
		turn = []
	current = next((s for s in turn if s.applies == "1" and not s.done), None)
	complete = not returned and not current and all(s.done for s in steps if s.applies == "1"
		and (s.position == "before" or body.get("covered_by")))
	return frappe._dict(body=body, request=r, steps=steps, current=current, returned=returned, events=events,
		complete=complete)


def _same_person(prog, step, user) -> str:
	"""§14.1: "1" when ``user`` may do the step only as the same person (the sender, or someone who did another step,
	and no one else of the step is free), "0" when they may do it plainly; refused otherwise."""
	if user not in step.eligible:
		frappe.throw(_("You are not one of the people for {0}").format(step.name), frappe.PermissionError)
	if user in {e.actor for e in step.by}:
		frappe.throw(_("You did {0} already").format(step.name))
	others = {e.actor for e in prog.events if e.kind in DONE and e.body.get("step") != step.no}

	def tied(u):
		return u == prog.request.requester or u in others

	if not tied(user):
		return "0"
	if step.rule == "any" and any(not tied(u) for u in step.eligible if u != user):
		frappe.throw(_("Someone else does {0}: you sent this request or did another of its steps").format(step.name),
			frappe.PermissionError)
	return "1"


def _names(users) -> list[str]:
	return [get_fullname(u) for u in users]


def waiting_text(step) -> str:
	left = [u for u in step.eligible if u not in {e.actor for e in step.by}] if step.rule == "all" else step.eligible
	return _("Waiting on {0}: {1}").format(", ".join(_names(left)) or _("no one on this project"), step.name)


def waiting_reason(request: str) -> str:
	"""The gate's words while an after-client acknowledgement is due (§14.3 item 5), else ""."""
	prog = progress(request)
	return waiting_text(prog.current) if prog and prog.current else ""


def covered_reason(vo) -> str:
	"""§14.3 item 7: a Variation its decision's approval covers still runs its own route; "" once that run is done on
	the terms saved now (or when no step of the route applies)."""
	latest = next(iter(subjects.requests_of(subjects.VO, vo.name)), None)
	prog = progress(latest.name) if latest and latest.status == INTERNAL else None
	if prog and prog.body.get("covered_by") == vo.decision_request and subjects.terms_hash(latest) == latest.terms_hash:
		if prog.complete:
			return ""
		if prog.current:
			return waiting_text(prog.current)
	if not starts_internal(resolve(vo, terms_for(vo), covered=vo.decision_request)):
		return ""
	return _("This variation's internal steps come first: send it through them")


# --- acting on a step -----------------------------------------------------------------------------------------------


def _staff(request):
	r = None if is_client(frappe.session.user) else read.readable(request)
	if not r:
		raise frappe.DoesNotExistError(_("Not found"))
	return r


@frappe.whitelist(methods=["POST"])
def step_approve(request: str, step: str, terms_hash: str) -> dict:
	"""Approve a before-client step on the terms the step sheet showed (§14.3 item 2)."""
	return _act(request, step, terms_hash, "internal_approved")


@frappe.whitelist(methods=["POST"])
def step_return(request: str, step: str, terms_hash: str, reason: str) -> dict:
	"""Return the request to its sender at a before-client step, with a reason (§14.3 item 3)."""
	return _act(request, step, terms_hash, "internal_returned", reason)


@frappe.whitelist(methods=["POST"])
def step_acknowledge(request: str, step: str, terms_hash: str) -> dict:
	"""Acknowledge an after-client step (§14.1: it cannot send the request back)."""
	return _act(request, step, terms_hash, "internal_acknowledged")


def _act(request, step, terms_hash, kind, reason="") -> dict:
	r0 = _staff(request)
	reason = cstr(reason).strip()[:REASON_MAX]
	if kind == "internal_returned" and not reason:
		frappe.throw(_("Say why you are returning it"))

	def _go() -> dict:
		terms_ok = log.terms_agree(r0.name, log.prehash(r0.name))  # the subject, the project, the request (D-459)
		r = frappe._dict(log.lock(r0.project, r0.name))
		prog = progress(r.name)
		current = prog.current if prog else None
		if not current or current.no != cstr(step):
			frappe.throw(_("This step is not waiting now. Reload the page."))
		if (kind == "internal_acknowledged") != (current.position == "after"):
			frappe.throw(_("A step after the client acknowledges only: it cannot send the request back") if
				current.position == "after" else _("This step approves or returns"))
		if terms_hash != r.terms_hash:
			frappe.throw(_("This page is out of date. Reload it and check the terms again."))
		if not terms_ok or not subjects.allowed(frappe.get_doc(r.subject_doctype, r.subject_name)):
			if r.status != INTERNAL:
				frappe.throw(_("The record changed since it was sent. It needs a new request."))
			subjects.supersede(r, "The terms changed")  # its steps start over with a new send (§14.3 item 6)
			return {"state": "replaced", "request": r.name}
		same = _same_person(prog, current, frappe.session.user)
		body = {"step": current.no, "name": current.name, "version": prog.body["version"], "same_person": same}
		if reason:
			body["reason"] = reason
		log.append_event(r.project, kind, request=r.name, terms_hash=r.terms_hash, body=body)
		line(r)
		doc = frappe.get_doc(REQUEST, r.name)
		if kind == "internal_returned":
			notify([r.requester], STEP_RETURNED, doc)
			return {"state": "returned", "request": r.name}
		after = progress(r.name)
		if after.current:
			ring(doc, after.current)
			return {"state": "waiting", "request": r.name, "step": after.current.no, "same_person": same == "1"}
		if r.status == INTERNAL and not prog.body.get("covered_by"):
			return {"state": "sent", "request": release(r), "same_person": same == "1"}
		if r.status == "Approved" and r.subject_doctype == subjects.DECISION:
			frappe.get_doc(subjects.DECISION, r.subject_name).db_set("status", "Decided")  # as decide does
		return {"state": "done", "request": r.name, "same_person": same == "1"}

	return log.retry_once(_go)


def ring(doc, step) -> None:
	"""The bell of each person the step waits on (§14.3 item 2)."""
	notify([u for u in step.eligible if u not in {e.actor for e in step.by}], STEP_WAITING, doc)


def line(r) -> None:
	"""A Team room System line for the step (§14.3 item 2); approvals.card draws its words."""
	card._post(frappe._dict(name=r.name, project=r.project, requester=r.requester), "Internal")


def started(request: str) -> None:
	"""A request sent into internal review: its first step's people rung."""
	prog = progress(request)
	if prog and prog.current:
		ring(frappe.get_doc(REQUEST, request), prog.current)


def release(a) -> str:
	"""The last before-client step passed (§14.3 item 4): a new Open request with the same frozen terms, copies and
	route goes to the client, its due date moved on by the days spent in review (Q5), and the request in review is
	superseded by it. Inside the lock (the subject, the project, then the request)."""
	from construction_core.approvals import api  # here: api imports this module

	if a.subject_doctype == subjects.DECISION:
		frappe.get_doc(subjects.DECISION, a.subject_name).db_set("status", "Waiting")  # Waiting starts now (§14.3 item 1)
	due = add_days(a.due_date, date_diff(nowdate(), a.creation)) if a.due_date else None
	releaser, frappe.session.user = frappe.session.user, a.requester  # the send is the sender's (owner, requested event)
	frappe.local.user_perms = None
	try:
		new = log.open_request(a.project, a.subject_doctype, a.subject_name,
			frozen_entries=list(json.loads(a.frozen_files or "{}").values()), requester=a.requester,
			requester_party=a.requester_party, decider_party=a.decider_party, subject_title=a.subject_title,
			due_date=due, note=a.note, retention_class=a.retention_class, retention_end=a.retention_end,
			statement_versions=json.loads(a.statement_versions or "{}"), predecessor=a.name)
	finally:
		frappe.session.user = releaser  # not frappe.set_user: in a request it would reset the session's sid and data
		frappe.local.user_perms = None  # rebuilt for the releaser when next asked
	log.append_event(a.project, "route_frozen", request=new, body={**_frozen(a.name), "from": a.name})
	subjects.supersede(a, "Passed the internal steps", successor=new)
	r = frappe.get_doc(REQUEST, new)
	api._client_mail(r, api._confirmed(r.project), _("{0} asks you to approve {1}").format(api._lead(), api._what(r)),
		api.REQUEST_MAIL, facts=api._facts(r))  # the card follows its requested event (approvals.card)
	return new


def client_approved(r, subject) -> None:
	"""After the client's approval (approvals.answer, approvals.recorded): the after-client acknowledgements are asked
	for (§14.3 item 5); a Decision is Decided once none is due."""
	prog = progress(r.name)
	if prog and prog.current:
		ring(frappe.get_doc(REQUEST, r.name), prog.current)
	elif subject.doctype == subjects.DECISION:
		subject.db_set("status", "Decided")  # the controller refuses a status save: the status follows the requests


def acknowledging(decision: str) -> str:
	"""Why a Waiting Decision cannot change: the client approved it and an after-client step is still due (§14.3 item
	5), so it is as final as a Decided one; "" otherwise (ClientDecision.validate, the preflight)."""
	r = next(iter(subjects.requests_of(subjects.DECISION, decision)), None)
	prog = progress(r.name) if r and r.status == "Approved" else None
	if not (prog and prog.current):
		return ""
	return _("The client approved this decision; it is waiting for {0}. It cannot change now.").format(prog.current.name)


def nudge(r) -> list[str] | None:
	"""Staff Nudge of a step (§14.3 item 8): its people rung again; None when no step waits."""
	prog = progress(r.name)
	if not (prog and prog.current):
		return None
	ring(frappe.get_doc(REQUEST, r.name), prog.current)
	return _names(u for u in prog.current.eligible if u not in {e.actor for e in prog.current.by})


def _since(request: str):
	"""When the current step began: the latest step, freeze or client approval of the request (UTC)."""
	return frappe.db.sql("""select max(at_utc) from `tabApproval Event` where request = %s and kind in
		('route_frozen', 'internal_approved', 'internal_acknowledged', 'approved')""", (request,))[0][0]


def due_of(request: str, step) -> object:
	from construction_core.discuss.parts.file_requests import working_days_after

	since = _since(request)
	return working_days_after(getdate(convert_utc_to_system_timezone(since)), cint(step.due_days) or 2) if since \
		else None


def remind() -> int:
	"""Daily (hooks; §14.3 item 8): a step past its due time rings its people and tells the sender, once per step.
	One request that fails never stops the others. Returns how many requests were told."""
	today_ = getdate(nowdate())
	told = 0
	for name in frappe.db.sql_list("""select distinct e.request from `tabApproval Event` e join `tabApproval Request` r
			on r.name = e.request where e.kind = 'route_frozen' and r.status in %s""", ((INTERNAL, "Approved"),)):
		point = "cc_route_remind_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(point)
		try:
			told += _remind_one(name, today_)
		except Exception:
			frappe.db.rollback(save_point=point)
			frappe.log_error(title="construction_core: internal step reminders failed", reference_doctype=REQUEST,
				reference_name=name)
		else:
			frappe.db.release_savepoint(point)
	return told


def _remind_one(name, today_) -> int:
	prog = progress(name)
	step = prog.current if prog else None
	due = due_of(name, step) if step else None
	if not due or today_ <= due:
		return 0
	since = convert_utc_to_system_timezone(_since(name)).replace(tzinfo=None)
	if frappe.db.exists("Notification Log", {"for_user": prog.request.requester, "document_type": REQUEST,
			"document_name": name, "email_header": key(STEP_OVERDUE), "creation": [">=", since]}):
		return 0
	waiting = [u for u in step.eligible if u not in {e.actor for e in step.by}]
	notify([*waiting, prog.request.requester], STEP_OVERDUE, frappe.get_doc(REQUEST, name))
	return 1


# --- what the screens read ---------------------------------------------------------------------------------------


def _who(s) -> str:
	if s["who"] == "people":
		return ", ".join(_names(s["people"]))
	return _(s["role"])


def _condition(s, currency="") -> str:
	if s["condition"] == "cost":
		return _("cost above {0}").format(f"{currency} {_money(s['above'])}".strip())
	if s["condition"] == "days":
		return _("more than {0} days").format(s["above"])
	return ""


def _money(value) -> str:
	amount = flt(value)
	return fmt_money(amount, precision=0 if amount == int(amount) else 2)


def _card(kind) -> dict:
	route = frappe.get_doc(ROUTE, kind) if frappe.db.exists(ROUTE, kind) else None
	v = latest_version(kind)
	return {"kind": kind, "steps": [{f: s.get(f) for f in ("step_name", "position", "who", "project_role", "staff_role",
		"people", "rule", "condition", "amount", "days", "due_days")} for s in route.steps] if route else [],
		"version": {"name": v.name, "sha256": v.sha256, "by": get_fullname(v.author), "at": f"{v.at_utc}Z"} if v else None}


def _reader():
	if is_client(frappe.session.user) or not frappe.has_permission(ROUTE, "read"):
		raise frappe.DoesNotExistError(_("Not found"))


@frappe.whitelist(methods=["GET"])
def routes(kind: str | None = None) -> dict:
	"""Settings → Approval steps (§14.6): one card per record kind, or the one asked, for staff; System Managers edit."""
	_reader()
	if kind and kind not in KINDS:
		frappe.throw(_("Unknown record kind"))
	return {"can_edit": "System Manager" in frappe.get_roles(), "routes": [_card(k) for k in ([kind] if kind else KINDS)]}


@frappe.whitelist(methods=["POST"])
def save_route(kind: str, steps: str | list) -> dict:
	"""A System Manager saves a record kind's steps (§14.2): checked, versioned and rung by the route's own save."""
	frappe.only_for("System Manager")
	if kind not in KINDS:
		frappe.throw(_("Unknown record kind"))
	rows = frappe.parse_json(steps) if isinstance(steps, str) else steps
	if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
		frappe.throw(_("The steps cannot be read"))
	fields = ("step_name", "position", "who", "project_role", "staff_role", "people", "rule", "condition", "amount",
		"days", "due_days")
	route = frappe.get_doc(ROUTE, kind) if frappe.db.exists(ROUTE, kind) else frappe.new_doc(ROUTE)
	route.record_kind = kind
	route.set("steps", [{f: ("\n".join(_people(r.get(f))) if f == "people" else r.get(f)) for f in fields if f in r}
		for r in rows])
	route.save()  # as the caller: the doctype's own permission (System Manager)
	return routes(kind)


def _record(doctype, name):
	if doctype not in KINDS or not isinstance(name, str) or not frappe.db.exists(doctype, name):
		raise frappe.DoesNotExistError(_("Not found"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return doc


def _line_for(doctype, terms, route, chosen=None) -> str:
	figures = _figures(doctype, terms, chosen)
	before = [s["name"] for s in route["steps"] if s["position"] == "before" and _applies(s, figures)]
	after = [s["name"] for s in route["steps"] if s["position"] == "after" and _applies(s, figures)]
	return " → ".join([*before, _("client"), *after])


@frappe.whitelist(methods=["GET"])
def preview(route: str, sample: str | None = None) -> dict:
	"""The settings preview line (§14.6): "VO-0007, PHP 84,000: QS check → Director approval → client → Director
	noted" for ``sample`` (a record of the route's kind the caller reads), else every step with its condition."""
	_reader()
	if route not in KINDS:
		frappe.throw(_("Unknown record kind"))
	v = latest_version(route)
	steps = json.loads(v.canonical)["steps"] if v else []
	if not sample:
		parts = [f'{s["name"]} ({_condition(s)})' if s["condition"] != "always" else s["name"] for s in steps]
		before = [p for p, s in zip(parts, steps) if s["position"] == "before"]
		return {"text": " → ".join([*before, _("client"), *(p for p, s in zip(parts, steps) if s["position"] == "after")])}
	doc = _record(route, sample)
	terms = terms_for(doc)
	cost, _days = _figures(route, terms)
	head = f'{terms.get("number") or doc.name}, {terms.get("currency") or ""} {_money(cost)}' if route in (
		subjects.VO, subjects.DECISION) else terms.get("number") or doc.name
	return {"text": f'{head.strip()}: {_line_for(route, terms, {"steps": steps})}'}


@frappe.whitelist(methods=["GET"])
def ask(doctype: str, name: str) -> dict:
	"""The Ask sheet's route for a record (§14.6): each step that applies, who can do it, and whether only the sender
	can (they then do it as the same person, §14.1)."""
	doc = _record(doctype, name)
	if is_client(frappe.session.user):
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.has_permission(PROJECT, "request_client_approval", doc=doc.project, throw=True)
	covered = doc.decision_request if doctype == subjects.VO and subjects.decision_covers(doc) else ""
	terms = terms_for(doc)
	route = resolve(doc, terms, covered)
	me = frappe.session.user
	return {"internal": starts_internal(route), "covered": bool(covered),
		"text": _line_for(doctype, terms, route) if route else "",
		"steps": [{"no": s["no"], "name": s["name"], "position": s["position"], "rule": s["rule"], "applies": s["applies"],
			"people": _names(s["eligible"]), "same_person": bool(s["eligible"]) and s["eligible"] == [me]}
			for s in (route or {}).get("steps") or []]}


def unstaffed(doc) -> list[str]:
	"""The preflight's (§14.2): the steps that apply, or may, with no one on the project to do them."""
	try:
		route = resolve(doc, terms_for(doc))
	except frappe.ValidationError:
		frappe.clear_last_message()
		return []  # the record's own checks say why it cannot be sent
	return [s["name"] for s in (route or {}).get("steps") or [] if s["applies"] != "0" and not s["eligible"]]


def view(r, user: str | None = None) -> dict | None:
	"""The request page's steps (§14.6): each with who, its rule, done by whom and when, the one waiting and its due
	day, a Return; and the step sheet for ``user``: the action, whether they may (and as the same person), the terms
	token. Staff only (approvals.staff)."""
	prog = progress(r.name)
	if not prog:
		return None
	user = user or frappe.session.user
	sheet = None
	if prog.current:
		try:
			same = _same_person(prog, prog.current, user)
			why = ""
		except (frappe.ValidationError, frappe.PermissionError) as e:
			same, why = "0", cstr(e)
			frappe.clear_last_message()
		sheet = {"step": prog.current.no, "name": prog.current.name,
			"action": "acknowledge" if prog.current.position == "after" else "approve", "can": not why, "reason": why,
			"same_person": same == "1", "terms_hash": r.terms_hash}
	return {"version": prog.body["version"], "covered": bool(prog.body.get("covered_by")), "complete": prog.complete,
		"from": prog.body.get("from") or "",
		"steps": [{"no": s.no, "name": s.name, "position": s.position, "rule": s.rule, "applies": s.applies,
			"people": _names(s.eligible), "done": s.done, "current": bool(prog.current) and s.no == prog.current.no,
			"due": str(due_of(r.name, s)) if prog.current and s.no == prog.current.no else "",
			"by": [{"name": get_fullname(e.actor), "at": f"{e.at_utc}Z", "same_person": e.body.get("same_person") == "1"}
				for e in s.by]} for s in prog.steps],
		"returned": {"by": get_fullname(prog.returned.actor), "at": f"{prog.returned.at_utc}Z",
			"step": prog.returned.body.get("name") or "", "reason": prog.returned.body.get("reason") or ""}
			if prog.returned else None,
		"waiting": waiting_text(prog.current) if prog.current else "", "sheet": sheet}


def timeline(r) -> list[dict]:
	"""The internal sign-off timeline of the evidence record (§14.3, managers only): each step event of the request and
	of the one it was sent on from, oldest first, with its route version."""
	prog = progress(r.name)
	return [{"kind": e.kind, "step": e.body.get("name") or "", "by": get_fullname(e.actor), "at": f"{e.at_utc}Z",
		"same_person": e.body.get("same_person") == "1", "reason": e.body.get("reason") or "",
		"version": e.body.get("version") or ""} for e in prog.events] if prog else []
