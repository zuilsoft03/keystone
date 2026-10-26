""""This was not me" (approvals design §3.7, §3.10; P3-78 M9, M11; threats T13, T23).

- **The link.** The decider's receipt (approvals.receipts) links to /approval-dispute#t=<token>. The token stays in the
  fragment, so opening the link sends nothing: the page posts it to ``view`` (what was answered; writes nothing) and, on
  the person's click, to ``not_me``. A mail scanner that opens the link records nothing (T23). Both are rate-limited per
  network address. A token works once, only while it is its answer's latest, and only the approver who answered (or the
  named signer of a recorded approval) holds one: theirs is the only receipt that carries it.
- **Staff** ``record`` a dispute that came by phone or email: the reason, how it came, and a proof file frozen after the
  client-file checks.
- **A dispute is a flag plus an event**: a ``disputed`` chain event (its network address in the evidence detail only),
  the approver's sessions ended, the managers alerted. The flag is the chain's (``disputed_open``). Its exits are
  ``dispute_resolved`` events: withdrawn by the client, upheld (the answer no longer counts; a new request is needed),
  or closed by a manager with a stated reason.
- **The gate** (M9): ``disputed_open(request)`` is what the staff gate reads: a dispute is open, or one was upheld. Each
  dispute records ``after_staff_act``: once the record has moved on, it alerts the managers and undoes nothing.
"""

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cstr

from construction_core.accounts.sessions import announce_end, end_sessions
from construction_core.approvals import api, canonical, log, read, receipts, subjects
from construction_core.approvals.answer import _detail
from construction_core.notifications import APPROVAL_DISPUTED, notify
from construction_core.onboarding import invites

OUTCOMES = ("withdrawn", "upheld", "closed")
HOW = ("phone", "email")
LIMIT, WINDOW = 10, 3600  # tries per network address and endpoint, an hour
DONE = "From now on the team does not rely on this approval until it is resolved."
BROKEN = "This link does not work. It may have been used already. If you need help, contact the team."


def _disputes(request: str, lock: bool = False) -> list[tuple[str, dict]]:
	"""(kind, body) of the request's dispute events, oldest first; ``lock``: a locking read, so the latest committed
	ones, inside the lock."""
	rows = frappe.db.sql(f"""select kind, canonical from `tabApproval Event` where request = %s
		and kind in ('disputed', 'dispute_resolved') order by seq{' for update' if lock else ''}""", (request,))
	return [(kind, json.loads(text)["body"]) for kind, text in rows]


def _state(disputes) -> str:
	""""" (none), "open", or the latest exit; "upheld" stays, the answer no longer counts."""
	state = ""
	for kind, body in disputes:
		if state == "upheld":
			break
		state = "open" if kind == "disputed" else body["outcome"]
	return state


def disputed_open(request: str) -> bool:
	"""Whether the team may not rely on the request's answer (§3.7, M9): a dispute is open, or one was upheld."""
	return _state(_disputes(request)) in ("open", "upheld")


def _acted(r) -> bool:
	"""Whether the staff act on the answer happened (§3.7): the record left the state its request was open in; for a
	Decision, a variation made from it."""
	if r.subject_doctype == subjects.DECISION:
		return bool(frappe.db.exists(subjects.VO, {"decision_request": r.name}))
	s = subjects.SUBJECTS[r.subject_doctype]
	return frappe.db.get_value(r.subject_doctype, r.subject_name, s.state) not in s.open


def _raise(e, user: str, extra: dict, detail=None) -> None:
	"""A dispute: its chain event, the approver's sessions ended, the managers alerted (§3.7)."""
	r = frappe.get_doc(log.REQUEST, e.request)
	log.append_event(e.project, "disputed", request=e.request, body={"answer": e.name, "user": user,
		"after_staff_act": "1" if _acted(r) else "0", **extra}, detail=detail)
	end_sessions(user)
	frappe.db.after_commit.add(lambda: announce_end(user))
	notify(invites._managers(frappe.get_doc(api.PROJECT, e.project)), APPROVAL_DISPUTED, r, actor=user)


# --- the link (guest) ---------------------------------------------------------------------------------------------


def _by_token(token, lock: bool = False):
	"""(answer event, approver) of a token while it is its answer's latest receipt token, unused, and the answer is not
	disputed now; else None."""
	if not isinstance(token, str) or not 20 <= len(token) <= 128:
		return None
	digest = canonical.sha256(token)
	rows = frappe.get_all(log.EVENT, filters={"kind": "receipt_sent", "canonical": ("like", f"%{digest}%")},
		pluck="request", limit=1)
	e = receipts.answer_of(rows[0]) if rows else None
	if not e:
		return None
	sent = (json.loads(t)["body"] for t in frappe.get_all(log.EVENT, filters={"request": e.request,
		"kind": "receipt_sent"}, pluck="canonical", order_by="seq desc"))
	latest = next((b for b in sent if b.get("token_sha256")), None)
	disputes = _disputes(e.request, lock)
	if not latest or latest["token_sha256"] != digest or latest["answer"] != e.name \
			or any(b.get("token_sha256") == digest for _k, b in disputes) or _state(disputes) in ("open", "upheld"):
		return None
	return e, latest["user"]


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=LIMIT, seconds=WINDOW)
def view(token: str) -> dict:
	"""What the link's answer was, for its page (§3.7). Writes nothing."""
	found = _by_token(token)
	if not found:
		raise frappe.PermissionError(_(BROKEN))
	e = found[0]
	r = frappe.get_doc(log.REQUEST, e.request)
	verb = _("approved") if e.kind == "approved" else _("returned")
	return {"summary": _("{0} was {1} in your name at {2}.").format(receipts.what(r), verb, receipts.when(e.at_utc))}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=LIMIT, seconds=WINDOW)
def not_me(token: str) -> dict:
	"""The page's confirm button (§3.7): the dispute, once, with the network address the request came from."""
	return log.retry_once(lambda: _not_me(token))


def _not_me(token) -> dict:
	found = _by_token(token)
	if found:
		log.lock(found[0].project, found[0].request)
		found = _by_token(token, lock=True)  # again inside the lock: two clicks at once dispute once
	if not found:
		raise frappe.PermissionError(_(BROKEN))
	e, user = found
	_raise(e, user, {"via": "link", "token_sha256": canonical.sha256(token)}, detail=_detail(""))
	return {"state": "disputed", "message": _(DONE)}


# --- staff ----------------------------------------------------------------------------------------------------------


def _managed(request):
	"""The request and its answer event, for a manager of its project (manage_clients)."""
	r = read.readable(request)
	e = receipts.answer_of(request) if r else None
	if not e:
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.has_permission(api.PROJECT, "manage_clients", doc=frappe.get_doc(api.PROJECT, r.project), throw=True)
	return r, e


@frappe.whitelist(methods=["POST"])
def record(request: str, reason: str, how: str, proof_file: str) -> dict:
	"""Staff record a dispute that came by phone or email (§3.7), since a person whose password was changed may not be
	able to sign in: a manager of the project, the approver's reason, how it came, a proof file of the project."""
	r, e = _managed(request)
	reason = cstr(reason).strip()[:api.NOTE_MAX]
	if how not in HOW:
		frappe.throw(_("Say how the client told you: by phone or by email."))
	if not reason:
		frappe.throw(_("Say what the client told you."))
	proof, proof_name = api._freeze_file(r.project, proof_file, checked=True)  # before the lock: the scan takes time

	def _record() -> dict:
		log.lock(e.project, e.request)
		if _state(_disputes(e.request, lock=True)) in ("open", "upheld"):
			frappe.throw(_("This approval is already disputed."))
		_raise(e, receipts.decider_of(e), {"via": how, "reason": reason, "proof": proof, "proof_name": proof_name})
		return {"state": "disputed"}

	return log.retry_once(_record)


@frappe.whitelist(methods=["POST"])
def resolve(request: str, outcome: str, reason: str) -> dict:
	"""A manager ends an open dispute (§3.7), with a stated reason: withdrawn by the client, upheld (the answer no
	longer counts and a new request is needed; a Decision approved and not yet made a variation needs one again), or
	closed."""
	r, e = _managed(request)
	reason = cstr(reason).strip()[:api.NOTE_MAX]
	if outcome not in OUTCOMES:
		frappe.throw(_("Choose how the dispute ends."))
	if not reason:
		frappe.throw(_("Say why."))

	def _resolve() -> dict:
		log._lock_subject(r.subject_doctype, r.subject_name)  # first (D-459): an upheld Decision's status changes
		log.lock(r.project, r.name)
		if _state(_disputes(r.name, lock=True)) != "open":
			frappe.throw(_("This approval has no open dispute."))
		log.append_event(r.project, "dispute_resolved", request=r.name, body={"answer": e.name, "outcome": outcome,
			"reason": reason})
		if outcome == "upheld" and e.kind == "approved" and r.subject_doctype == subjects.DECISION and not _acted(r):
			frappe.get_doc(subjects.DECISION, r.subject_name).db_set("status", subjects.NEEDS)
		return {"state": outcome}

	return log.retry_once(_resolve)
