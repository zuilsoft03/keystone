"""What staff read about client approvals (approvals design §3.2-§3.4, §3.9, §3.12, §4.1; P3-80, O1-O4): the
Discussion Approvals tab (``requests``), the request page (``page``), the Ask sheet's preflight (``preflight``), Print for
signature (``print_form``), a record page's gated move (``gate``), the evidence record and its signature picture
(``evidence``, ``signature``) and the project's approval settings with its Ready checklist (``settings``). Each is a GET
that writes nothing; the writes are approvals.api, recorded, dispute, receipts and credentials.

- **Who**: never a client (``_staff``: every read is a "Not found" to one, even an approver who reads the request
  itself). A request is read through its own rule (approvals.read) as the caller, so staff of another project get
  nothing. ``preflight`` needs request_client_approval on the project; ``settings`` read on it.
- **Managers only** (``_manager``: manage_clients on the project, or a System Manager, as credentials._contact): the
  evidence record, with Approval Evidence Detail (network address, browser and system, location), and the signature
  picture. No other staff and no client reads them; ``page`` carries none of it.
- **Plain fields**: the timeline is built from a fixed set of keys per event kind, never an event's whole body (an
  answer's holds the session hash and the sealed signature's address, a receipt's the token hash).
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, date_diff, escape_html, get_fullname, getdate
from werkzeug.wrappers import Response

from construction_core.approvals import (agreement, api, canonical, card, credentials, log, read, receipts, routes,
	subjects)
from construction_core.approvals import preflight as checks
from construction_core.approvals.answer import signature_picture
from construction_core.onboarding.mail import brand_name
from construction_core.permissions import is_client

PROJECT = api.PROJECT
# the Approvals tab's filters (§3.12), each a card.state; Waiting leaves out the Overdue ones, as the tab counts them.
# P3-82 (§14.6): "internal_review", and "waiting_on_me": the requests whose step waits on the reader (across groups)
SHOWS = ("waiting", "overdue", "approved", "returned", "disputed", "recorded", "replaced_or_voided", "internal_review",
	"waiting_on_me")
LIMIT = 200  # shortcut: newest first, a project's last 200 requests; page the tab once a project has more
FIELDS = ["name", "project", "status", "subject_doctype", "subject_name", "subject_title", "due_date", "creation",
	"snapshot", "requester", "note", "terms_hash", "frozen_files", "predecessor", "successor"]
TIMELINE = ("requested", "agreed", "opened", "approved", "returned", "receipt_sent", "receipt_failed", "disputed",
	"dispute_resolved", "recorded", "voided", "superseded", "internal_review", *log.INTERNAL_EVENTS)  # P3-82: staff only
# a printable page: its own styles, no script, nothing loaded, framed by us only
PRINT_CSP = ("default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
	"frame-ancestors 'self'; sandbox")
NO_APPROVER = "No approver is set up"


# --- who reads ----------------------------------------------------------------------------------------------------


def _not_found():
	raise frappe.DoesNotExistError(_("Not found"))


def _staff(request):
	"""The request, for staff who read it through its own rule; anyone else (a client included) "Not found"."""
	r = None if is_client(frappe.session.user) else read.readable(request)
	return r or _not_found()


def _project(project):
	if is_client(frappe.session.user) or not isinstance(project, str) or not frappe.db.exists(PROJECT, project):
		_not_found()
	return frappe.get_doc(PROJECT, project)


def _is_manager(project) -> bool:
	return "System Manager" in frappe.get_roles() or bool(frappe.has_permission(PROJECT, "manage_clients", doc=project))


def _manager(project):
	if "System Manager" in frappe.get_roles():
		frappe.has_permission(PROJECT, "read", doc=project, throw=True)
	else:
		frappe.has_permission(PROJECT, "manage_clients", doc=project, throw=True)


# --- the Approvals tab (§3.12) ------------------------------------------------------------------------------------


def _filter(state: str, r, today) -> str | None:
	if state == "waiting":
		return "overdue" if r.due_date and getdate(r.due_date) < today else "waiting"
	return "replaced_or_voided" if state in ("replaced", "voided") else None if state == "draft" else state


def _decider(answer) -> str:
	body = answer.body
	return body.get("signer_name") or (body.get("who") or {}).get("full_name") or get_fullname(answer.actor)


@frappe.whitelist(methods=["GET"])
def requests(project: str, show: str | None = None) -> dict:
	"""One project's requests as the caller reads them, newest first: {approvers, counts, rows}. ``show``: one of
	SHOWS, or every request."""
	if is_client(frappe.session.user):
		_not_found()
	if show and show not in SHOWS:
		frappe.throw(_("Unknown filter"))
	rows = frappe.get_list(log.REQUEST, filters={"project": project, "status": ["!=", "Draft"]}, fields=FIELDS,
		order_by="creation desc", limit=LIMIT) if isinstance(project, str) else []
	known, today = card.chain([r.name for r in rows]), getdate()
	people = [get_fullname(u) for u, ok in api.approvers(project).items() if ok] if rows else []
	out, counts = [], dict.fromkeys(SHOWS, 0)
	for r in rows:
		k = known[r.name]
		state = card.state(r.status, k)
		group = _filter(state, r, today)
		if group:
			counts[group] += 1
		# shortcut: one route read per row in review or approved; read the tab's routes in one pass if it grows
		steps = routes.view(r) if r.status in (log.INTERNAL, "Approved") else None
		mine = bool(steps and steps["sheet"] and steps["sheet"]["can"])
		counts["waiting_on_me"] += mine
		if show and not (mine if show == "waiting_on_me" else group == show):
			continue
		terms, answer = json.loads(r.snapshot)["terms"], k["answer"]
		out.append({"name": r.name, "kind": r.subject_doctype, "reference": terms.get("number") or r.subject_name,
			"title": r.subject_title or terms.get("title") or "", "state": state, "group": group,
			"approvers": people if r.status == "Open" else [_decider(answer)] if answer else [],
			"due_date": str(r.due_date or ""), "age_days": date_diff(today, r.creation),
			"by": _decider(answer) if answer else "", "at": f"{answer.at}Z" if answer else "",
			# shortcut: one check per approved row; fine for a tab of LIMIT rows, read in one pass if it grows
			"needs_reconfirmation": state == "approved" and credentials.needs_reconfirmation(r.name),
			"waiting_on": steps["waiting"] if steps else "", "waiting_on_me": mine})  # P3-82: "Waiting on Maria: QS check"
	return {"project": project, "approvers": people, "counts": counts, "rows": out}


# --- the request page (§3.12, O4) -----------------------------------------------------------------------------------


def _approvers(project) -> list[dict]:
	"""Each approver with their Project Member row (for Send reset link and Confirm), the second staff confirmation,
	their agreement and whether they must reset their password before approving (O2)."""
	member = dict(frappe.get_all("Project Member", filters={"parenttype": PROJECT, "parent": project},
		fields=["user", "name"], as_list=True))
	return [{"member": member.get(u), "name": get_fullname(u), "confirmed": ok, "state": _(api.CONFIRMED if ok else
		api.WAITING), "agreed": bool(agreement.accepted(project, u)), "must_reset": credentials.must_reset(u)}
		for u, ok in api.approvers(project).items()]


def _events(r) -> list:
	"""The request's chain events for the timeline, and its approvers' agreements since it was sent (an agreement is a
	project event, §3.5 item 2), oldest first."""
	who = tuple(api.approvers(r.project)) or ("",)
	return frappe.db.sql("""select name, kind, actor, at_utc, seq, hash, canonical from `tabApproval Event`
		where (request = %(r)s and kind in %(kinds)s) or (project = %(p)s and kind = 'agreed' and actor in %(who)s
			and seq > (select min(seq) from `tabApproval Event` where request = %(r)s))
		order by seq""", {"r": r.name, "p": r.project, "kinds": TIMELINE, "who": who}, as_dict=True)


def _option(terms, key) -> str:
	return next((o["label"] for o in terms.get("options") or [] if o["key"] == key), "") if key else ""


def _line(e, terms) -> dict:
	"""One timeline row in plain fields: who (the decider for an answer), when, and what this kind says."""
	body = json.loads(e.canonical)["body"]
	out = {"kind": e.kind, "at": f"{e.at_utc}Z", "by": get_fullname(e.actor)}
	if e.kind in receipts.ANSWERS:
		out.update(by=get_fullname(receipts.decider_of(e)), reason=body.get("reason") or "",
			option=_option(terms, body.get("option")), method=body.get("method") or "", label=body.get("label") or "",
			signed=(body.get("signature") or {}).get("kind") or "")
	elif e.kind in ("receipt_sent", "receipt_failed"):
		out.update(to=get_fullname(body["user"]), role=body["role"], error=body.get("error") or "")
	elif e.kind == "opened":
		out["file"] = body.get("file") or ""
	elif e.kind == "disputed":
		out.update(by=get_fullname(body["user"]), via=body.get("via") or "", reason=body.get("reason") or "")
	elif e.kind == "dispute_resolved":
		out.update(outcome=body["outcome"], reason=body.get("reason") or "")
	elif e.kind == "recorded":
		out.update(event=e.name, signer=body["signer_name"], method=body["method"], label=body["label"],
			option=_option(terms, body.get("option")))
	elif e.kind in ("voided", "superseded"):
		out.update(reason=body.get("reason") or "", successor=body.get("successor") or "")
	elif e.kind in ("internal_approved", "internal_returned", "internal_acknowledged"):
		out.update(step=body.get("name") or "", reason=body.get("reason") or "", same_person=body.get("same_person") == "1")
	elif e.kind == "route_frozen":
		out.update(version=body.get("version") or "", sent_from=body.get("from") or "")
	return out


def _receipts(events) -> dict:
	"""The receipts of the request's latest answer: {"state": "" (no answer) | "not_sent" | "sent" | "failed",
	"people": [{name, role, state, at}]}, each person's latest try."""
	answers = [e.seq for e in events if e.kind in receipts.ANSWERS]
	if not answers:
		return {"state": "", "people": []}
	latest = {}
	for e in events:
		if e.seq > answers[-1] and e.kind in ("receipt_sent", "receipt_failed"):
			body = json.loads(e.canonical)["body"]
			latest[body["user"]] = {"name": get_fullname(body["user"]), "role": body["role"],
				"state": "sent" if e.kind == "receipt_sent" else "failed", "at": f"{e.at_utc}Z"}
	people = list(latest.values())
	state = "not_sent" if not people else "failed" if any(p["state"] == "failed" for p in people) else "sent"
	return {"state": state, "people": people}


def gate_reason(doc) -> dict:
	"""A record's gated move as its page shows it (§3.11, O4): {required, to, reason, fix, request}. ``reason`` is ""
	when the move may go ahead; ``fix`` "approvers" when no approver is set up."""
	s = subjects.SUBJECTS[doc.doctype]
	latest = next(iter(subjects.requests_of(doc.doctype, doc.name)), None)
	required = bool(s.gated) and bool(cint(doc.get("client_approval_required"))) and bool(cint(
		frappe.db.get_value(PROJECT, doc.project, "cc_portal_approvals")))
	why = subjects.gate_reason(doc, latest) if s.gated else ""
	return {"required": required, "to": list(s.gated), "reason": why, "fix": "approvers" if why == _(NO_APPROVER) else "",
		"request": latest.name if latest else None}


def _step(key: str, label: str, reason: str = "", **extra) -> dict:
	return {"key": key, "label": _(label), "enabled": not reason, "reason": reason, **extra}


def next_steps(r, known: dict, state: str, manager: bool, events=(), internal=None) -> list[dict]:
	"""The request page's next step (§3.12, ApprovalNextSteps), the first one the main button: each {key, label,
	enabled, reason}; a gated move disabled with why (O4). P3-82 (§14.3): an internal step for the reader first
	("internal_step", with its step and action); a request returned at a step is edited and sent again, or closed."""
	internal = routes.view(r) if internal is None else internal
	sheet = internal["sheet"] if internal else None
	if state == "internal_review" and internal and internal["returned"]:
		return [_step("edit_send_again", "Edit and send again"), _step("close_request", "Close request")]
	first = [_step("internal_step", sheet["name"], sheet["reason"], step=sheet["step"], action=sheet["action"])] 		if sheet else []
	if state == "internal_review" and not (internal and internal["covered"] and internal["complete"]):
		return first
	return first + _next_steps(r, known, state, manager, events)


def _next_steps(r, known, state, manager, events) -> list[dict]:
	if state == "disputed":
		if known["dispute"] == "upheld":
			return [_step("edit_send_again", "Edit and send again")]
		return [_step("record_note", "Record a note"),
			_step("resolve", "Resolve", "" if manager else _("A manager of the project resolves a dispute"))]
	if state == "returned":
		return [_step("edit_send_again", "Edit and send again"), _step("close_request", "Close request")]
	if state == "replaced" and r.successor:
		return [_step("open_successor", "Open the newer request", request=r.successor)]
	if state in ("replaced", "voided"):
		return [_step("edit_send_again", "Edit and send again")]
	evidence = [_step("evidence", "Open the evidence record")] if manager and state in ("approved", "recorded") else []
	pending = [e for e in events if e.kind in ("recorded", *receipts.ANSWERS)]
	if state == "waiting" and pending and pending[-1].kind == "recorded":  # another manager confirms it (§3.9)
		return [_step("confirm_record", "Confirm the recorded approval", request=r.name, event=pending[-1].name)]
	doc = frappe.get_doc(r.subject_doctype, r.subject_name)
	if r.subject_doctype == subjects.DECISION:  # no gated move: a priced one makes its variation (§3.3)
		if state == "waiting" or not subjects.priced(doc) or frappe.db.exists(subjects.VO, {"decision_request": r.name}):
			return evidence
		return [_step("make_variation", "Make the variation", subjects.unrelied(r.name, True)), *evidence]
	gate = gate_reason(doc)
	if state == "waiting" and not gate["required"]:
		return []  # nothing waits on this answer: the record moves as it always did
	if gate["request"] != r.name or (state != "waiting" and doc.get(subjects.SUBJECTS[r.subject_doctype].state)
			not in subjects.SUBJECTS[r.subject_doctype].open):
		return evidence  # a newer request, or the record moved on already
	return [_step("approve_change", "Approve the change", gate["reason"], to=gate["to"], fix=gate["fix"]), *evidence]


def _files(r) -> list[dict]:
	return [{**{k: e[k] for k in ("key", "name", "type", "size", "rev", "shown_sha256")},
		"url": f"/api/method/construction_core.approvals.file?request={r.name}&key={e['key']}"}
		for e in json.loads(r.frozen_files or "{}").values()]


@frappe.whitelist(methods=["GET"])
def page(request: str) -> dict:
	"""The request page for staff (§3.12): the frozen terms and copies, the approvers with their states, the timeline,
	the receipts and the next step. No evidence detail, signature or hash of a session (``evidence`` is managers')."""
	r = _staff(request)
	known = card.chain([r.name])[r.name]
	state, terms, events = card.state(r.status, known), json.loads(r.snapshot)["terms"], _events(r)
	manager, answer, internal = _is_manager(r.project), known["answer"], routes.view(r)
	return {"request": r.name, "project": r.project, "kind": r.subject_doctype, "subject": r.subject_name,
		"reference": terms.get("number") or r.subject_name, "title": r.subject_title or terms.get("title") or "",
		"status": r.status, "state": state, "due_date": str(r.due_date or ""),
		"overdue": _filter(state, r, getdate()) == "overdue", "note": r.note or "",
		"requested_by": get_fullname(r.requester), "requested_at": f"{events[0].at_utc}Z" if events else "",
		"predecessor": r.predecessor or "", "successor": r.successor or "", "void_reason": known["reason"],
		"dispute": known["dispute"], "terms": terms, "terms_hash": r.terms_hash, "files": _files(r),
		"approvers": _approvers(r.project),
		"answer": {"kind": answer.kind, "by": _decider(answer), "at": f"{answer.at}Z",
			"reason": answer.body.get("reason") or "", "option": _option(terms, answer.body.get("option")),
			"method": answer.body.get("method") or ""} if answer else None,
		"timeline": [_line(e, terms) for e in events], "receipts": _receipts(events),
		"next": next_steps(r, known, state, manager, events, internal), "manager": manager,
		"internal": internal}  # P3-82 (§14.6): the steps, who and when, and the step sheet's data


@frappe.whitelist(methods=["GET"])
def gate(doctype: str, name: str) -> dict:
	"""A record page's gated move (§3.11, O4), for staff who read the record."""
	if is_client(frappe.session.user) or doctype not in subjects.SUBJECTS or not isinstance(name, str) \
			or not frappe.db.exists(doctype, name):
		_not_found()
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return gate_reason(doc)


# --- the Ask sheet's preflight (§3.2, §3.4, O2) ---------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def preflight(project: str, doctype: str | None = None, name: str | None = None) -> dict:
	"""The preflight (approvals.preflight) for staff who send requests on the project: {ready, reasons, approvers}.
	Each reason is {key, reason, fix}; each approver carries Agreed and must_reset, which never block the sending."""
	_project(project)
	frappe.has_permission(PROJECT, "request_client_approval", doc=project, throw=True)
	if doctype:
		if doctype not in subjects.SUBJECTS or not isinstance(name, str) or not frappe.db.exists(doctype, name):
			_not_found()
		frappe.get_doc(doctype, name).check_permission("read")
	reasons = checks.preflight(project, doctype, name)
	return {"ready": not reasons, "reasons": reasons, "approvers": _approvers(project)}


# --- Print for signature (§3.4, §3.9) -------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def print_form(request: str):
	"""A one-page form of the frozen terms for a client who answers on paper: the request, the locked line, the files'
	fingerprints, the terms fingerprint and a signature block. Printed from the browser; nothing here runs a script."""
	r = _staff(request)
	terms, e = json.loads(r.snapshot)["terms"], escape_html
	project = frappe.db.get_value(PROJECT, r.project, "project_name")
	lines = agreement.lines(r)
	if r.subject_doctype == subjects.DECISION:
		what = "".join(f"<li><span class=box></span> {e(o['label'])}: {e(lines[o['key']])}</li>"
			for o in terms.get("options") or [])
		what = f"<p>{e(_('Tick the one option you choose.'))}</p><ul class=options>{what}</ul>"
	else:
		what = f"<p>{e(lines['record'])}</p>"
	files = "".join(f"<li>{e(f['name'])} (rev {e(f['rev'])}): {e(f['shown_sha256'])}</li>" for f in _files(r))
	sign = "".join(f"<div class=field><span>{e(_(label))}</span></div>" for label in ("Name", "Signature", "Date"))
	html = f"""<!doctype html><html lang=en><head><meta charset=utf-8><title>{e(r.name)}</title><style>
body{{font:14px/1.5 system-ui,sans-serif;color:#111;background:#fff;max-width:720px;margin:24px auto;padding:0 16px}}
h1{{font-size:20px;margin:0 0 4px}} .muted{{color:#555}} code{{word-break:break-all;font-size:12px}}
.box{{display:inline-block;width:14px;height:14px;border:1px solid #111;vertical-align:middle}}
.options{{list-style:none;padding:0}} .field{{border-bottom:1px solid #111;height:48px;margin:16px 0 0;
display:flex;align-items:flex-end}} .field span{{font-size:12px;color:#555;transform:translateY(18px)}}
@page{{margin:16mm}} @media print{{body{{margin:0}}}}</style></head><body>
<p class=muted>{e(brand_name())} · {e(project)}</p>
<h1>{e(r.subject_title or terms.get('title') or '')}</h1>
<p class=muted>{e(_(r.subject_doctype))} {e(terms.get('number') or r.subject_name)} · {e(_('Request'))} {e(r.name)}
{f" · {e(_('Due'))} {e(str(r.due_date))}" if r.due_date else ""}</p>
{what}
{f"<p>{e(_('Files'))}:</p><ul>{files}</ul>" if files else ""}
<p class=muted>{e(_('Fingerprint of these terms'))}: <code>{e(r.terms_hash)}</code></p>
{sign}
</body></html>"""
	return Response(html, status=200, content_type="text/html; charset=utf-8", headers={
		"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff",
		"Cross-Origin-Resource-Policy": "same-origin", "Content-Security-Policy": PRINT_CSP,
		"Content-Disposition": f"inline; filename=print-{r.name}.html"})


# --- the evidence record (§3.12, §4.1; managers) --------------------------------------------------------------------


def _parties(project, before_seq) -> dict:
	"""The client party and contract reference as the chain held them before ``before_seq`` (None: now), with who
	entered the party and when ("entered by [manager] on [date]", §3.2 item 2)."""
	filters = {"project": project, "kind": "settings", **({"seq": ["<", before_seq]} if before_seq else {})}
	out, last = {}, None
	for row in frappe.get_all(log.EVENT, filters=filters, fields=["actor", "at_utc", "canonical"], order_by="seq asc"):
		body = json.loads(row.canonical)["body"]
		party = (body.get("client_legal_name"), body.get("client_address"))
		if party != last:
			out.update(entered_by=get_fullname(row.actor), entered_at=f"{row.at_utc}Z")
			last = party
		out.update({k: body.get(k) or "" for k in ("client_legal_name", "client_address", "contract_document",
			"contract_date", "contract_clause", "contract_file_name")})
	return out


@frappe.whitelist(methods=["GET"])
def evidence(request: str) -> dict:
	"""The evidence record (§3.12, §4.1) for the project's managers: the summary, the answer and its option, the
	signature (by ``signature``'s URL, never inline), the evidence block from Approval Evidence Detail, the timeline,
	the four fingerprints and the receipts; "Interim" while the request is open, "Final" after."""
	r = _staff(request)
	_manager(r.project)
	known, terms, events = card.chain([r.name])[r.name], json.loads(r.snapshot)["terms"], _events(r)
	e = receipts.answer_of(r.name)
	body = json.loads(e.canonical)["body"] if e else {}
	text = json.loads(e.canonical) if e else {}
	sig = body.get("signature") or {}
	detail = frappe.db.get_value(log.DETAIL, {"event": e.name}, list(log.DETAIL_FIELDS), as_dict=True) if e else None
	who = body.get("who") or {}
	head = frappe.db.sql("""select seq, hash from `tabApproval Event` where project = %s order by seq desc limit 1""",
		(r.project,), as_dict=True)
	option = next((o for o in terms.get("options") or [] if o["key"] == body.get("option")), None)
	out = {"request": r.name, "project": r.project,
		"project_name": frappe.db.get_value(PROJECT, r.project, "project_name"),
		"stage": "Interim" if r.status in ("Draft", "Open", log.INTERNAL) else "Final", "status": r.status,
		"state": card.state(r.status, known),
		"summary": {"kind": r.subject_doctype, "reference": terms.get("number") or r.subject_name,
			"title": r.subject_title or terms.get("title") or "", "revision": terms.get("revision") or "",
			"currency": terms.get("currency") or "", "total": terms.get("total") or "", "days": terms.get("days") or "",
			"requested_by": get_fullname(r.requester), "requested_at": f"{events[0].at_utc}Z" if events else "",
			"due_date": str(r.due_date or "")},
		"parties": _parties(r.project, e.seq if e else None),
		"answer": {"kind": e.kind, "by": get_fullname(receipts.decider_of(e)), "at": f"{e.at_utc}Z",
			"reason": body.get("reason") or "", "option": {k: option[k] for k in ("key", "label", "cost_difference",
				"time_difference")} if option else None} if e else None,
		"signature": {"kind": sig.get("kind") or "", "typed_name": sig.get("typed_name") or "",
			"name_matches": sig.get("name_matches") or "", "sha256": sig.get("sha256") or "",
			"url": f"/api/method/construction_core.approvals.staff.signature?request={r.name}" if sig.get("file") else ""}
			if sig else None,
		"evidence": {"time_zone": text.get("time_zone") or "",
			"account": {"name": who.get("full_name") or "", "email": who.get("email") or "", "kind": who.get("kind") or ""},
			**{k: (detail or {}).get(k) or "" for k in ("network_address", "ip_trust", "browser", "system", "user_agent")},
			"location": json.loads(detail.location) if detail and detail.location else None,
			"session": {k: (body.get("session") or {}).get(k) or "" for k in ("started", "two_step", "password_step")},
			"statement_versions": (body.get("agreement") or {}).get("versions") or {},
			"recorded": {"method": body["method"], "label": body.get("label") or "", "given_at": body.get("given_at") or "",
				"proof_name": body.get("proof_name") or "", "original": body.get("original") or "",
				"recorded_by": get_fullname(body.get("recorded_by")), "confirmed_by": get_fullname(body.get("confirmed_by")),
				"same_person": body.get("same_person") == "1"} if body.get("method") else None} if e else None,
		"timeline": [_line(x, terms) for x in events], "receipts": _receipts(events),
		"fingerprints": {"version": r.terms_hash, "signature": sig.get("sha256") or "",
			"answer": {"seq": e.seq, "hash": e.hash} if e else None,
			"chain_head": {"seq": head[0].seq, "hash": head[0].hash} if head else None},
		"internal": routes.timeline(r)}  # P3-82 (§14.3): the firm's internal sign-offs, managers only
	out["fingerprints"]["document"] = canonical.sha256(json.dumps(out, sort_keys=True, default=str))
	return out


@frappe.whitelist(methods=["GET"])
def signature(request: str):
	"""A drawn signature's picture, unsealed, for the project's managers only (the evidence record shows it)."""
	r = _staff(request)
	_manager(r.project)
	e = receipts.answer_of(r.name)
	sealed = (json.loads(e.canonical)["body"].get("signature") or {}).get("file") if e else None
	png = signature_picture(sealed) if sealed else None
	if not png:
		_not_found()
	return Response(png, status=200, content_type="image/png", headers={
		"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff",
		"Cross-Origin-Resource-Policy": "same-origin", "Content-Security-Policy": PRINT_CSP,
		"Content-Disposition": f"inline; filename=signature-{r.name}.png"})


# --- the project's approval settings (§3.2, ApprovalSettings) -------------------------------------------------------

READY = (("contract", ("portal_approvals", "contract"), "Contract confirmation with reference"),
	("client_party", ("client_party",), "Client party entered"),
	("evidence_mailbox", ("evidence_mailbox",), "Evidence mailbox tested"),
	("approver", ("approver",), "The first approver confirmed by a second staff member"))


@frappe.whitelist(methods=["GET"])
def settings(project: str) -> dict:
	"""A project's approval settings for staff who read the project: the set-up values with who confirmed the contract
	and entered the client party, the evidence mailbox, each client contact as an approver or not (with must_reset),
	and the Ready checklist with the preflight's reasons. The writes are approvals.api's and credentials'."""
	doc = _project(project)
	frappe.has_permission(PROJECT, "read", doc=doc, throw=True)
	manager = _is_manager(project)
	confirmation = next((r for r in frappe.get_all(log.EVENT, filters={"project": project, "kind": "settings"},
		fields=["actor", "at_utc", "canonical"], order_by="seq desc")
		if json.loads(r.canonical)["body"].get("confirmation")), None)
	designated = {b["user"]: b for _actor, b in api._designations(project)}
	found = api.approvers(project)
	member = dict(frappe.get_all("Project Member", filters={"parenttype": PROJECT, "parent": project},
		fields=["user", "name"], as_list=True))
	contacts = [{"member": member.get(u), "name": get_fullname(u), "approver": u in found,
		"confirmed": bool(found.get(u)), "state": _(api.CONFIRMED if found.get(u) else api.WAITING) if u in found else "",
		"authority_name": (designated.get(u) or {}).get("authority_name") or "" if u in found else "",
		"agreed": u in found and bool(agreement.accepted(project, u)), "must_reset": credentials.must_reset(u)}
		for u in api._contacts(project)]
	mailbox = frappe.db.get_single_value(api.SETTINGS, "evidence_mailbox", cache=False) or ""
	reasons = checks.preflight(project)
	failed = {r["key"] for r in reasons}
	items = [{"key": key, "label": _(label), "done": not failed.intersection(keys)} for key, keys, label in READY]
	return {"project": project, "manager": manager, "values": api._settings(doc),
		"confirmation": {"text": _(api.CONFIRMATION), "by": get_fullname(confirmation.actor),
			"at": f"{confirmation.at_utc}Z"} if confirmation else None,
		"client_party": {k: v for k, v in _parties(project, None).items() if k in ("entered_by", "entered_at")},
		"mailbox": {"address": mailbox if manager else credentials.masked(mailbox) if mailbox else "",
			"confirmed": bool(cint(frappe.db.get_single_value(api.SETTINGS, "evidence_mailbox_confirmed", cache=False)))},
		"contacts": contacts,
		"ready": {"ready": not reasons, "items": items, "done": sum(i["done"] for i in items), "of": len(items),
			"reasons": reasons}}
