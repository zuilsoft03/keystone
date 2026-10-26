"""Verify the approvals ledger (design §4.6; §6 threats "Direct database edits", "The receipt is suppressed", "Backups
miss evidence"; §14.5): ``bench --site <site> execute construction_core.approvals.verify.run`` and the daily job
(digest.daily calls ``run(job=True)`` first). Nothing here writes, but a failed daily run's ``verify_failed`` events.

- **The chain** of each project, recomputed from its rows: sequence 1..n, each previous hash and hash (the genesis from
  seq 1's own site), and the canonical text against the event's columns, the high water and out-of-order flag too.
- **Requests**: the snapshot hashes to terms_hash, every terms event carries it, the columns are the first terms event's
  (log.request_body), the status is the chain's; an Approved final record's live terms are its approved ones or the
  last ``changed_after_decision``'s (drift).
- **Evidence**: each answer's detail row exists and its salted commitment recomputes, unless a ``retention_cleared``
  event names it gone or a ``location_cleared`` one names its location emptied; every frozen copy reads back by its
  SHA-256 (a signature picture retention cleared may be gone); every answer older than RECEIPT_DUE has its
  ``receipt_sent``; the evidence mailbox's Email Account has not changed since the chain's last mailbox event; each
  anchor's heads and each outside head are in their chains.
- **Routes** (§14.5): each ``route_frozen`` names an Approval Route Version whose steps it froze; each internal step
  names a step of its request's frozen route, in the state that step runs in.
- **Set-up**: the live switches and each approver's may_approve and state are the chain's last values.

``heads``: outside heads (receipts, digests, the restore drill), a list of {"project", "seq", "hash"} or a path to a
JSON file holding one. Each problem names its project, the seq of the event at fault (0: none), the check and a detail.
"""

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import cint, convert_utc_to_system_timezone, cstr, get_system_timezone, getdate

from construction_core.approvals import api, canonical, frozen, log, retention

RECEIPT_DUE = timedelta(hours=24)
ANSWERS = ("approved", "returned")
FILE_KEYS = ("contract_file", "authority", "proof", "sha256")  # body keys holding a frozen copy's SHA-256
STEP_STATES = {"internal_approved": (log.INTERNAL,), "internal_returned": (log.INTERNAL,),
	"internal_acknowledged": ("Approved", log.INTERNAL)}  # In internal review: a covered Variation's after-steps
PROJECT_MEMBER = "Project Member"


def run(heads=None, project: str | None = None, job: bool = False) -> dict:
	"""{"ok", "problems": [{project, seq, check, detail}], "heads": {project: {seq, hash}}}. ``job``: the daily run,
	which writes a failing project's ``verify_failed`` event and mails the evidence mailbox."""
	projects = [project] if project else frappe.get_all(log.EVENT, pluck="project", distinct=True, order_by="project")
	problems, out = [], {}
	for p in projects:
		found, head = [], None
		try:
			head = _project(p, found.append)
		except Exception as e:  # a row edited into a shape the checks cannot read must still raise the alarm
			found.append((0, "verify", f"the check could not run: {type(e).__name__}"))
		problems += [{"project": p, "seq": seq, "check": check, "detail": detail} for seq, check, detail in found]
		if head:
			out[p] = head
	problems += _outside(heads, None if project is None else {project})
	if job and problems:
		_report(problems)
	return {"ok": not problems, "problems": problems, "heads": out}


def _project(project, bad) -> dict | None:
	events = frappe.get_all(log.EVENT, filters={"project": project}, fields=["*"], order_by="seq asc")
	texts = _chain(events, bad)
	_requests(project, events, texts, bad)
	_evidence(project, events, texts, bad)
	_routes(events, texts, bad)
	_setup(project, events, texts, bad)
	return {"seq": events[-1].seq, "hash": events[-1].hash} if events else None


def _body(texts, e) -> dict:
	body = texts.get(e.name, {}).get("body")
	return body if isinstance(body, dict) else {}


# --- the chain ------------------------------------------------------------------------------------------------------


def _utc(value) -> datetime | None:
	try:
		return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
	except (TypeError, ValueError):
		return None


def _chain(events, bad) -> dict:
	"""Each event's parsed canonical text by name; a text that is not one is a problem and left out."""
	texts, prev, high, last = {}, None, None, 0
	for e in events:
		if e.seq != last + 1:
			bad((e.seq, "sequence", f"after {last}"))
		last = e.seq
		try:
			t = json.loads(e.canonical)
			if not isinstance(t, dict):
				raise ValueError
		except (TypeError, ValueError):
			bad((e.seq, "canonical", "not a canonical text"))
			prev = e.hash
			continue
		texts[e.name] = t
		if e.seq == 1:
			prev = canonical.genesis(cstr(t.get("site")), cstr(t.get("project")))
		if e.prev_hash != prev:
			bad((e.seq, "link", "the previous hash is not the previous event's"))
		try:
			if canonical.link(e.prev_hash, e.canonical) != e.hash:
				bad((e.seq, "hash", "the hash is not its canonical text's"))
		except ValueError:
			bad((e.seq, "hash", "the previous hash is not a hash"))
		at, water = _utc(t.get("at")), _utc(t.get("high_water"))
		late = bool(high and at and at < high)
		high = max(high, at) if high and at else (at or high)
		if (t.get("canonical_version") != canonical.VERSION or ("site" in t) != (e.seq == 1)
				or (t.get("project"), t.get("seq"), t.get("kind"), t.get("actor"), t.get("request"), t.get("terms_hash"),
					t.get("out_of_order"), at, water) != (e.project, str(e.seq), e.kind, e.actor, e.request or None,
					e.terms_hash or None, str(e.out_of_order), e.at_utc, e.high_water)
				or (water, t.get("out_of_order")) != (high, "1" if late else "0")):
			bad((e.seq, "columns", "the columns or the times are not the canonical text's"))
		prev = e.hash
	return texts


def _has(project, seq, hash_) -> bool:
	return bool(frappe.db.exists(log.EVENT, {"project": project, "seq": seq, "hash": hash_}))


def _heads_in(heads, project_of_problem, seq, check, only=None) -> list:
	"""The problems of a list of heads, each {"project", "seq", "hash"}, against the chains; ``only``: these projects."""
	out = []
	for h in heads if isinstance(heads, list) else [heads]:
		h = h if isinstance(h, dict) else {}
		p, s, x = h.get("project"), cint(h.get("seq")), h.get("hash")
		if only is not None and p not in only:
			continue
		if not (isinstance(p, str) and p and s > 0 and isinstance(x, str) and canonical.HEX64.match(x)):
			out.append({"project": project_of_problem or cstr(p), "seq": seq, "check": check, "detail": "not a head"})
		elif not _has(p, s, x):
			out.append({"project": project_of_problem or p, "seq": seq or s, "check": check,
				"detail": f"{p} has no event {s} with that hash"})
	return out


def _outside(heads, only) -> list:
	if heads is None:
		return []
	if isinstance(heads, str):
		try:
			with open(heads, encoding="utf-8") as fh:
				heads = json.load(fh)
		except (OSError, ValueError):
			return [{"project": "", "seq": 0, "check": "outside_head", "detail": "the heads file cannot be read"}]
	return _heads_in(heads, None, 0, "outside_head", only)


# --- requests -------------------------------------------------------------------------------------------------------


def _requests(project, events, texts, bad) -> None:
	first, states, terms = {}, {}, {}
	for e in events:
		if not e.request:
			continue
		if e.kind in log.TERMS_EVENTS:
			first.setdefault(e.request, e)
			terms.setdefault(e.request, []).append(e)
		if e.kind in log.STATE_AFTER:
			states[e.request] = e
	rows = {r.name: r for r in frappe.get_all(log.REQUEST, filters={"project": project}, fields=["*"])}
	for name in dict.fromkeys([*first, *rows]):
		r, e = rows.get(name), first.get(name)
		if not (r and e):
			bad((e.seq if e else 0, "request", f"{name}: no request row" if e else f"{name}: no terms event"))
			continue
		t = texts.get(e.name, {})
		try:
			snap = json.loads(r.snapshot)
			agree = (canonical.text(log.request_body(r)) == canonical.text(t.get("body") or {})
				and snap["project"] == project and snap["subject"] == {"type": r.subject_doctype, "name": r.subject_name}
				and snap["frozen"] == json.loads(r.frozen_files))
		except (ValueError, TypeError, KeyError):
			agree = False
		if not agree:
			bad((e.seq, "request", f"{name}: its columns are not its terms event's"))
		if canonical.sha256(r.snapshot or "") != r.terms_hash or any(x.terms_hash != r.terms_hash for x in terms[name]):
			bad((e.seq, "snapshot", f"{name}: the snapshot is not its terms_hash"))
		last = states.get(name)
		if r.status != (log.STATE_AFTER[last.kind] if last else None):
			bad((last.seq if last else e.seq, "status", f"{name}: the status is not the chain's"))
		elif r.status == "Approved":
			_drift(r, last, events, texts, bad)


def _drift(r, approved, events, texts, bad) -> None:
	"""An Approved final record's live terms are its approved ones, or the last changed_after_decision's (L6)."""
	from construction_core.approvals import routes, subjects  # here: they import far more than a verify needs

	s = subjects.SUBJECTS.get(r.subject_doctype)
	if not s or not frappe.db.exists(r.subject_doctype, r.subject_name):
		return
	if not (frappe.db.get_value(r.subject_doctype, r.subject_name, s.state) in s.final
			or (r.subject_doctype == subjects.DECISION and routes.acknowledging(r.subject_name))):
		return
	changed = [e for e in events if e.request == r.name and e.kind == "changed_after_decision"]
	expected = _body(texts, changed[-1]).get("terms_hash") if changed else r.terms_hash
	if (subjects.terms_hash(r) or "") != expected:
		bad(((changed[-1] if changed else approved).seq, "drift", f"{r.name}: the record changed since its approval"))


# --- evidence -------------------------------------------------------------------------------------------------------


def _evidence(project, events, texts, bad) -> None:
	cleared, located = _clearings(project, events, texts, bad)
	gone = {cstr(b.get("signature")) for b in cleared.values()} - {""}
	details = {d.event: d for d in frappe.get_all(log.DETAIL, filters={"project": project}, fields=["*"])}
	# the decider's own receipt (the one with "This was not me"), not a co-approver's
	receipts = {cstr(_body(texts, e).get("answer")) for e in events
		if e.kind == "receipt_sent" and _body(texts, e).get("role") == "decider"}
	due = datetime.now(timezone.utc).replace(tzinfo=None) - RECEIPT_DUE
	for e in events:
		t, body = texts.get(e.name, {}), _body(texts, e)
		if "detail_commitment" in t:
			_detail(e, t["detail_commitment"], details.get(e.name), e.name in cleared, located, bad)
		for sha in files_of(e.kind, body):
			if sha not in gone and frozen.read(sha) is None:
				bad((e.seq, "frozen", f"{sha} is missing or changed"))
		if e.kind in ANSWERS and e.at_utc < due and e.name not in receipts:
			bad((e.seq, "receipt", f"no receipt_sent for {e.name}"))
	for r in frappe.get_all(log.REQUEST, filters={"project": project}, fields=["name", "frozen_files"]):
		try:
			shown = [x.get("shown_sha256") for x in json.loads(r.frozen_files or "{}").values()]
		except (ValueError, AttributeError):
			continue  # the request check names it
		first = next((e for e in events if e.request == r.name and e.kind in log.TERMS_EVENTS), None)
		for sha in shown:
			if frozen.read(sha) is None:
				bad((first.seq if first else 0, "frozen", f"{r.name}: {sha} is missing or changed"))
	_mailbox(events, texts, bad)
	for e in events:
		if e.kind == "anchor":
			for p in _heads_in(_body(texts, e).get("heads") or [], project, e.seq, "anchor"):
				bad((p["seq"], p["check"], p["detail"]))


def _clearings(project, events, texts, bad) -> tuple[dict, set]:
	"""The retention and location clearings that excuse a missing or changed detail row, each only when it could have
	been the job's: after a completion of its project, past its request's retention end, naming an answer of its own
	request and that answer's signature file. A clearing appended by a database edit must also forge those."""
	done = retention.completions(project)
	by_name = {e.name: e for e in events}
	cleared, located = {}, set()
	for e in events:
		if e.kind not in ("retention_cleared", "location_cleared"):
			continue
		body, day = _body(texts, e), getdate(convert_utc_to_system_timezone(e.at_utc))  # the job's and Version's dates
		a = by_name.get(cstr(body.get("event")))
		ok = bool(a and a.request == e.request and e.seq > a.seq) and any(c <= day for c in done)
		if ok and e.kind == "retention_cleared":
			r = frappe.db.get_value(log.REQUEST, e.request, ["retention_end", "retention_class"], as_dict=True)
			sign = _body(texts, a).get("signature")
			file = cstr(sign.get("file") if isinstance(sign, dict) else "")
			ok = bool(r) and cstr(body.get("signature")) == file and any(day > retention.end_of(r, c) for c in done if c <= day)
		if not ok:
			bad((e.seq, "clearing", "this clearing is not one the retention job could have written"))
		elif e.kind == "retention_cleared":
			cleared[cstr(body.get("event"))] = body
		else:
			located.add((cstr(body.get("event")), cstr(body.get("detail"))))
	return cleared, located


def files_of(kind, body) -> list[str]:
	"""The frozen copies an event's body names: a contract, an authority, a proof, a signature picture, an evidence PDF
	(its ``sha256`` or ``file``)."""
	shas = [body.get(k) for k in FILE_KEYS if k != "sha256" or kind == "evidence_pdf"]
	if kind == "evidence_pdf":
		shas.append(body.get("file"))
	if isinstance(body.get("signature"), dict):
		shas.append(body["signature"].get("file"))
	return [s for s in shas if isinstance(s, str) and s]


def _detail(e, commitment, d, retained, located, bad) -> None:
	if d is None:
		if not retained:
			bad((e.seq, "detail", "the evidence detail row is missing"))
		return
	values = {f: d.get(f) or "" for f in log.DETAIL_FIELDS}
	if canonical.sha256(f"{d.salt}\n{canonical.text(values)}") == commitment:
		return
	# shortcut: once location is cleared the commitment covers a value that is gone, so the other fields of that row
	# go unchecked; upgrade by having location_cleared commit to the remaining fields
	if not (d.location == "" and (e.name, d.name) in located):
		bad((e.seq, "detail", "the evidence detail row is not its commitment"))


def _mailbox(events, texts, bad) -> None:
	"""The evidence mailbox's Email Account (it keeps no track_changes) modified after the chain's last mailbox event."""
	# a chain with no mailbox event joined with the mailbox in force in its first settings event; a later settings event
	# must not move the baseline, or a switch change would hide an account edit
	last = next((e for e in reversed(events) if e.kind == "evidence_mailbox"), None) or next((e for e in events
		if e.kind == "settings" and _body(texts, e).get("evidence_mailbox")), None)
	if not last:
		return
	body = _body(texts, last)
	address = body.get("address") if last.kind == "evidence_mailbox" else body.get("evidence_mailbox")
	if not address:
		return
	zone = ZoneInfo(get_system_timezone())
	for a in frappe.get_all("Email Account", filters={"email_id": address}, fields=["name", "modified"]):
		modified = a.modified.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
		if modified > last.at_utc:
			bad((last.seq, "email_account", f"{a.name} changed after the mailbox event"))


# --- routes (§14.5) -------------------------------------------------------------------------------------------------


def _routes(events, texts, bad) -> None:
	frozen_of, state = {}, {}
	for e in events:
		body = _body(texts, e)
		if e.kind == "route_frozen":
			v = frappe.db.get_value(log.ROUTE_VERSION, cstr(body.get("version")), ["sha256", "canonical"], as_dict=True)
			try:
				steps = json.loads(v.canonical)["steps"] if v else None
			except (ValueError, KeyError, TypeError):
				steps = None
			froze = [{k: x for k, x in s.items() if k not in ("eligible", "applies")} for s in body.get("steps") or []
				if isinstance(s, dict)]
			if not v or canonical.sha256(v.canonical or "") != v.sha256 or v.sha256 != body.get("version_sha256") \
					or steps != froze:
				bad((e.seq, "route", "the frozen route is not its Approval Route Version"))
			frozen_of[e.request] = body
		elif e.kind in STEP_STATES:
			route = frozen_of.get(e.request) or {}
			step = next((s for s in route.get("steps") or [] if isinstance(s, dict) and s.get("no") == body.get("step")),
				None)
			if (not step or body.get("version") != route.get("version") or state.get(e.request) not in STEP_STATES[e.kind]
					or (e.kind == "internal_acknowledged") != (step.get("position") == "after")):
				bad((e.seq, "route", "the step is not one of its request's frozen route, in its state"))
		if e.request and e.kind in log.STATE_AFTER:
			state[e.request] = log.STATE_AFTER[e.kind]


# --- set-up ---------------------------------------------------------------------------------------------------------


def _setup(project, events, texts, bad) -> None:
	"""The live switches and approvers against the chain's last settings and designation events (§2 rule 5)."""
	settings = next((e for e in reversed(events) if e.kind == "settings"), None)
	if settings and frappe.db.exists(api.PROJECT, project):
		body = _body(texts, settings)
		if {k: cstr(body.get(k)) for k in api.SET_UP} != api._settings(frappe.get_doc(api.PROJECT, project)):
			bad((settings.seq, "settings", "the project's switches are not its last settings event's"))
	latest = {}
	for e in events:
		if e.kind == "designation":
			latest[cstr(_body(texts, e).get("user"))] = e
	rows = frappe.get_all(PROJECT_MEMBER, filters={"parenttype": api.PROJECT, "parent": project},
		fields=["user", "may_approve", "approver_state"])
	live = {r.user: (cint(r.may_approve), cstr(r.approver_state)) for r in rows}
	for user, e in latest.items():
		b = _body(texts, e)
		may, state = live.get(user, (0, ""))
		if may != cint(b.get("may_approve")) or (may and state != cstr(b.get("state"))):
			bad((e.seq, "designation", "an approver's row is not their last designation event's"))
	if any(may and user not in latest for user, (may, _state) in live.items()):
		bad((0, "designation", "an approver with no designation event"))


# --- the daily job ----------------------------------------------------------------------------------------------------


def _report(problems) -> None:
	"""A failing project's verify_failed event (the checks and seqs only: no personal data) and one mail to the evidence
	mailbox."""
	by = {}
	for p in problems:
		by.setdefault(p["project"], set()).add((p["check"], cint(p["seq"])))
	lines = []
	for project, found in sorted(by.items()):
		checks, seqs = sorted({c for c, _s in found}), sorted({s for _c, s in found if s})
		lines.append(f"{project or 'outside heads'}: {', '.join(checks)}" + (f" (events {', '.join(map(str, seqs))})"
			if seqs else ""))
		if project and frappe.db.exists(api.PROJECT, project):
			log.append_event(project, "verify_failed", body={"checks": checks, "seqs": seqs})
	mailbox = frappe.db.get_single_value(api.SETTINGS, "evidence_mailbox")
	if mailbox:
		api._mail([mailbox], "Approval records failed their daily check", ["The daily check of the approval records "
			"found problems. Run construction_core.approvals.verify.run on the site for the detail.", *lines])
