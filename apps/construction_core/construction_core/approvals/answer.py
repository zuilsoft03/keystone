"""How a client answers an approval request (approvals design §3.5, §4.1, §4.5; P3-78 M1, M3-M6, M8).

- ``sheet`` (M1): what the portal's approval sheet shows, through the request's read rule only: the frozen terms and
  copies, a Decision's options, the due date, the note and the approvers. For an approver of an Open request, also the
  agreement to accept, the password step, "Must reset password before approving", the locked lines, the location switch
  and the version tokens ``decide`` sends back. Anyone else gets the read-only sheet.
- ``password`` (§3.5 item 3, M3): the password step, due when the sign-in started more than 24 hours ago or the session
  was idle more than 1 hour, as marked by the first request after the gap (``note_idle``, before Frappe resets it). Its
  own counter, TRIES wrong passwords an hour per account in the cache; Frappe's sign-in counter is never touched.
- ``decide`` (§3.5 item 7): a client's own browser session (§4.5), then every check inside one transaction under the lock
  order subject, project, request (D-459). One refusal class per sentence (WORDS). A repeated answer id returns the first
  result and writes nothing (M5). A record changed since it was sent supersedes the request and approves nothing: that
  is returned, not raised, so the supersede is kept.
- Signatures (M4): typed (two words, compared with the account's name; a difference is recorded) or drawn (a PNG that
  passes the client-file checks, is not blank, is re-encoded by clean_image, frozen and sealed with the site key;
  ``signature_picture`` opens it for the receipts).
- Location (M6): only with the project's switch on and the client's tick; its state always, a shared position coarsened
  to 2 decimals, both in Approval Evidence Detail only; a "no" is remembered as the person's default.
"""

import base64
import binascii
import hmac
import io
import json
import re
import socket
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, cstr, get_datetime, get_fullname, now_datetime
from frappe.utils.data import convert_utc_to_system_timezone

from construction_core import __version__, client_files
from construction_core.accounts import two_step
from construction_core.approvals import agreement, api, canonical, credentials, frozen, log, read, subjects
from construction_core.approvals.api import NOTE_MAX, PROJECT, _email, approvers
from construction_core.permissions import CLIENT_ROLE, client_section_open
from construction_core.providers.storage import clean_image

EVENT = "cc_approval_changed"  # ids only, to each reader's own room (D-394)
ANSWER_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
STEP_IDLE, STEP_AGE = timedelta(hours=1), timedelta(hours=24)
TRIES, WINDOW = 5, 3600
STEP_DAY = 86400  # the cache markers' life: a session's step is never older than a day
SIGNATURE_MAX = 512 * 1024
LOCATION_STATES = ("shared", "denied", "unavailable", "timed_out", "not_supported")
LOCATION_NO = "cc_approval_location_no"  # the person's remembered "no" (a user default)
WORDS = {
	"NotBrowserSession": "Please answer from your own signed-in portal page.",
	"NotClient": "Only the client's approvers can answer here.",
	"ApprovalsClosed": "Approvals are closed for this project now.",
	"AlreadyAnswered": "{0} already {1} this at {2}. Nothing more to do.",
	"Replaced": "The team replaced this with a newer version.",
	"Voided": "This request was voided by the team: {0}.",
	"NotApprover": "You are no longer an approver for this project.",
	"NeedsAgreement": "Accept the portal agreement first.",
	"PasswordNeeded": "Enter your password first.",
	"WrongPassword": "That password is not right. {0} tries left.",
	"PasswordLocked": "Ask the team for a paper approval.",
	"PageOutdated": "This page is out of date. Reload it and check the terms again.",
}


class NotBrowserSession(frappe.PermissionError):
	"""An API key, a token, Basic, OAuth, a set_user with no request, an impersonated session, a missing or wrong CSRF
	token, or a site with CSRF checks off (§4.5, T6, T12)."""


class NotClient(frappe.PermissionError):
	"""Staff, a System Manager or a partner (until P3-32) answering (T5, T32)."""


class ApprovalsClosed(frappe.PermissionError):
	"""The project's preflight names a reason (portal approvals off, closed, the site switch)."""


class AlreadyAnswered(frappe.ValidationError):
	pass


class Replaced(frappe.ValidationError):
	pass


class Voided(frappe.ValidationError):
	pass


class NotApprover(frappe.PermissionError):
	pass


class NeedsAgreement(frappe.PermissionError):
	pass


class PasswordNeeded(frappe.PermissionError):
	pass


class WrongPassword(frappe.ValidationError):
	pass


class PasswordLocked(frappe.PermissionError):
	pass


class PageOutdated(frappe.ValidationError):
	"""A version token the page showed (terms, statements, location switch) is no longer current."""


# --- who answers, from which session --------------------------------------------------------------------------------


def answerer() -> str:
	"""The client answering through their own signed-in browser session (§4.5, M8): a request, no Authorization header,
	CSRF checks on and the header matching the session's token, a session id that is not the user's name and exists in
	Sessions, session data with a start, and no impersonation; then a client account with the client role, read from
	the database (T5, T6, T12, T32)."""
	user, sid = frappe.session.user, frappe.session.get("sid")
	data = frappe._dict(frappe.session.get("data") or {})
	request = getattr(frappe.local, "request", None)
	if (not request or request.method != "POST" or frappe.get_request_header("Authorization")
			or frappe.conf.get("ignore_csrf") or not sid or sid in ("Guest", user) or not data.get("creation")
			or not data.get("csrf_token") or data.get("impersonated_by") or data.get("audit_user")
			or not hmac.compare_digest(cstr(frappe.get_request_header("X-Frappe-CSRF-Token")), cstr(data.csrf_token))
			or not _session_row(sid, user)):
		frappe.throw(_(WORDS["NotBrowserSession"]), NotBrowserSession)
	if frappe.db.get_value("User", user, "user_type") != "Website User" or not frappe.db.exists("Has Role",
			{"parenttype": "User", "parent": user, "role": CLIENT_ROLE}):
		frappe.throw(_(WORDS["NotClient"]), NotClient)
	return user


def _session_row(sid, user) -> bool:
	t = frappe.qb.DocType("Sessions")  # not a DocType: the table only
	return bool(frappe.qb.from_(t).select(t.sid).where((t.sid == sid) & (t.user == user)).run())


# --- the password step (§3.5 item 3, M3) ----------------------------------------------------------------------------


def _step_due(data, sid) -> bool:
	"""Due when the sign-in (or the last password step) is more than a day old, the session is idle more than an hour
	now, or it was marked due (``note_idle`` or the sheet) and no step followed."""
	now, ok = now_datetime(), frappe.cache.get_value(f"cc:approval:step_ok:{sid}")
	marked = frappe.cache.get_value(f"cc:approval:step_due:{sid}")
	started = get_datetime(data.get("creation"))
	return (now - max(started, ok or started) > STEP_AGE
		or now - get_datetime(data.get("last_updated") or data.get("creation")) > STEP_IDLE
		or bool(marked and (not ok or ok < marked)))


def note_idle() -> None:
	"""before_request, after Frappe resumes the session and before this request's end refreshes its last_updated (Frappe
	does that on the first request after 600 s): that first request after an idle hour (a page load, a reload, the
	socket's user info, a boot) marks the step due for the session, so the sheet and decide still see the gap."""
	# shortcut: Frappe writes last_updated at most every 600 s, so the hour can count from up to 10 minutes before the
	# last request; keep our own per-request time in the cache if that matters
	s = frappe.session
	sid, seen = s.get("sid"), (s.get("data") or {}).get("last_updated")
	if seen and sid not in (None, "Guest", s.get("user")) and now_datetime() - get_datetime(seen) > STEP_IDLE:
		frappe.cache.set_value(f"cc:approval:step_due:{sid}", now_datetime(), expires_in_sec=STEP_DAY)


def _tries_key(user) -> str:
	return frappe.cache.make_key(f"cc:approval:pw_tries:{user}")


def locked(user) -> bool:
	return cint(frappe.cache.get(_tries_key(user))) >= TRIES


def check_password(user, password) -> None:
	"""The step's own counter: TRIES wrong passwords an hour per account (M3), counted atomically in the cache; Frappe's
	sign-in failure counter is never touched (two_step._password_ok)."""
	key = _tries_key(user)
	if locked(user):
		frappe.throw(_(WORDS["PasswordLocked"]), PasswordLocked)
	if two_step._password_ok(user, password):
		frappe.cache.delete(key)
		return
	if frappe.cache.incr(key) == 1:
		frappe.cache.expire(key, WINDOW)
	left = max(0, TRIES - cint(frappe.cache.get(key)))
	if not left:
		frappe.throw(_(WORDS["PasswordLocked"]), PasswordLocked)
	frappe.throw(_(WORDS["WrongPassword"]).format(left), WrongPassword)


@frappe.whitelist(methods=["POST"])
def password(password: str | None = None) -> dict:
	"""The password step before signing: passed, this session needs it again only after a day or an idle hour."""
	user = answerer()
	check_password(user, password)
	frappe.cache.set_value(f"cc:approval:step_ok:{frappe.session.sid}", now_datetime(), expires_in_sec=STEP_DAY)
	return {"ok": True}


# --- the sheet (M1) -------------------------------------------------------------------------------------------------


def _last_state(name) -> dict | None:
	rows = frappe.get_all(log.EVENT, filters={"request": name, "kind": ("in", tuple(log.STATE_AFTER))},
		fields=["kind", "actor", "at_utc", "canonical"], order_by="seq desc", limit=1)
	return rows[0] if rows else None


def _by(e) -> str:
	"""Who answered: the client, or a staff-recorded approval's signer, never the manager who confirmed it."""
	from construction_core.approvals.receipts import decider_of  # here: receipts imports this module

	return get_fullname(decider_of(e))


def _decided(name) -> dict | None:
	e = _last_state(name)
	return {"status": log.STATE_AFTER[e.kind], "by": _by(e), "at": str(e.at_utc) + "Z"} if e else None


def _tokens(r, switch) -> dict:
	return {"terms_hash": r.terms_hash, "agreement": agreement.VERSION, "lines": agreement.LINES_VERSION,
		"notice": agreement.NOTICE_VERSION, "location": "1" if cint(switch) else "0"}


@frappe.whitelist(methods=["GET"])
def sheet(request: str) -> dict:
	"""The approval sheet (§3.5 items 1-5) as the caller may read it."""
	r = read.readable(request)
	if not r:
		raise frappe.DoesNotExistError(_("Not found"))
	user, terms = frappe.session.user, json.loads(r.snapshot)["terms"]
	p = frappe.db.get_value(PROJECT, r.project, ["project_name", "cc_device_location"], as_dict=True)
	found = approvers(r.project)
	out = {"request": r.name, "project": r.project, "project_name": p.project_name, "kind": r.subject_doctype,
		"reference": r.subject_name, "title": r.subject_title or terms.get("title") or "", "status": r.status,
		"terms": terms, "options": terms.get("options") or [], "due_date": str(r.due_date or ""), "note": r.note or "",
		"approvers": [get_fullname(u) for u, ok in found.items() if ok],
		"files": [{**{k: e[k] for k in ("key", "name", "type", "size", "rev")},
			"url": f"/api/method/construction_core.approvals.file?request={r.name}&key={e['key']}"}
			for e in json.loads(r.frozen_files or "{}").values()],
		"decided": None if r.status == "Open" else _decided(r.name), "can_answer": False}
	if r.status != "Open" or not found.get(user) or frappe.session.get("sid") in (None, "Guest", user):
		return out  # the read-only sheet
	sid, data = frappe.session.sid, frappe._dict(frappe.session.get("data") or {})
	due = bool(data.get("creation")) and _step_due(data, sid)
	if due:  # read now: this request's own end resets the idle time decide would see
		frappe.cache.set_value(f"cc:approval:step_due:{sid}", now_datetime(), expires_in_sec=STEP_DAY)
	on = cint(p.cc_device_location)
	return {**out, "can_answer": True,
		"agreement": None if agreement.accepted(r.project, user) else {"version": agreement.VERSION,
			"text": agreement.agreement_text(r.project)},
		"password_step": due, "password_locked": locked(user),
		"must_reset": _(credentials.MUST_RESET) if credentials.must_reset(user) else "",
		"lines": agreement.lines(r),
		"location": {"on": bool(on), "notice": agreement.NOTICE if on else "", "notice_version": agreement.NOTICE_VERSION,
			"remembered_no": bool(on and frappe.defaults.get_user_default(LOCATION_NO))},
		"tokens": _tokens(r, on)}


# --- signatures (M4) ------------------------------------------------------------------------------------------------


def _fernet():
	from cryptography.fernet import Fernet
	from frappe.utils.password import get_encryption_key

	return Fernet(get_encryption_key().encode())


def signature_picture(sealed_sha: str) -> bytes | None:
	"""A drawn signature's PNG, unsealed with the site key; the receipts (§3.6) attach it."""
	return frozen.read(sealed_sha, unseal=_fernet().decrypt)


def _blank(png: bytes) -> bool:
	from PIL import Image

	with Image.open(io.BytesIO(png)) as image:
		flat = Image.alpha_composite(Image.new("RGBA", image.size, "white"), image.convert("RGBA")).convert("L")
	low, high = flat.getextrema()
	return low == high


def _signature(signature, user) -> dict:
	"""The evidence of a signature: typed or drawn. A drawn picture's plain bytes come back as ``png``, stored inside
	the lock once every check has passed."""
	s = frappe.parse_json(signature) if isinstance(signature, str) else signature
	if not isinstance(s, dict) or s.get("kind") not in ("typed", "drawn"):
		frappe.throw(_("Add your signature first"))
	if s["kind"] == "typed":
		typed = " ".join(cstr(s.get("name")).split())
		if len(typed.split(" ")) < 2 or len(typed) > 140:
			frappe.throw(_("Type your first and last name"))
		full = " ".join(cstr(get_fullname(user)).split())
		return {"kind": "typed", "typed_name": typed, "name_matches": "1" if typed.casefold() == full.casefold() else "0",
			"sha256": canonical.sha256(typed)}
	try:
		png = base64.b64decode(cstr(s.get("picture")).removeprefix("data:image/png;base64,"), validate=True)
	except (binascii.Error, ValueError):
		png = b""
	if not png or len(png) > SIGNATURE_MAX:
		frappe.throw(_("Add your signature first"))
	client_files.check_type("png")
	client_files.check_signature("png", png)
	client_files.check_structure("png", png)
	png = clean_image(png, "png")
	if _blank(png):
		frappe.throw(_("Add your signature first"))
	return {"kind": "drawn", "typed_name": "", "name_matches": "", "sha256": canonical.sha256(png), "png": png}


# --- location (M6) and the personal detail (§4.1) -------------------------------------------------------------------


def _location(location, on) -> str:
	"""The location result, kept only in Approval Evidence Detail: nothing while the switch is off; "not_ticked" or a
	state; a shared position to 2 decimals (about 1 km) with its accuracy. A malformed one is "unavailable"."""
	if not on:
		return ""
	loc = frappe.parse_json(location) if isinstance(location, str) and location else location
	if not isinstance(loc, dict) or not loc:
		return json.dumps({"state": "not_ticked"})
	state = loc.get("state") if loc.get("state") in LOCATION_STATES else "unavailable"
	if state != "shared":
		return json.dumps({"state": state})
	try:
		lat, lon, acc = (float(loc[k]) for k in ("latitude", "longitude", "accuracy"))
	except (KeyError, TypeError, ValueError):
		lat = lon = acc = float("nan")
	if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= acc < 1e7):  # NaN fails every comparison
		return json.dumps({"state": "unavailable"})
	return json.dumps({"state": "shared", "latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}",
		"accuracy": f"{acc:.0f}", "label": "reported by the device"}, sort_keys=True)


def _trust(address: str, peer: str) -> str:
	"""§4.7: a forwarded address is believed only when the peer is the frontend (nginx, which itself trusts only the edge
	subnet); from any other peer the address is "untrusted"."""
	if address == peer:
		return "peer"
	try:
		frontend = socket.gethostbyname_ex("frontend")[2]
	except OSError:
		frontend = []
	return "forwarded" if peer in frontend else "untrusted"


def _detail(location: str) -> dict:
	"""Read here, never from a whitelisted method's parameters (§7)."""
	agent = cstr(frappe.get_request_header("User-Agent"))[:log.DETAIL_MAX]
	browser = next((n for n, m in (("Edge", "Edg/"), ("Chrome", "Chrome/"), ("Firefox", "Firefox/"),
		("Safari", "Safari/")) if m in agent), "")
	system = next((n for n, m in (("Android", "Android"), ("iOS", "iPhone"), ("iPadOS", "iPad"), ("Windows", "Windows"),
		("macOS", "Mac OS X"), ("Linux", "Linux")) if m in agent), "")
	peer = cstr(frappe.local.request.environ.get("REMOTE_ADDR"))
	address = cstr(getattr(frappe.local, "request_ip", "")) or peer
	return {"network_address": address, "ip_trust": _trust(address, peer), "user_agent": agent,
		"browser": browser, "system": system, "wsgi_peer": peer, "location": location}


# --- decide (§3.5 item 7) -------------------------------------------------------------------------------------------


def _result(e) -> dict:
	return {"state": e.kind, "request": e.request, "event": e.name, "receipt_to": credentials.masked(_email(e.actor))}


def _publish(r) -> None:
	from construction_core.discuss.live import client_members, staff_members

	users = staff_members(r.project) + (client_members(r.project) if client_section_open(log.REQUEST, r.project) else [])
	for u in dict.fromkeys(users):
		frappe.publish_realtime(EVENT, {"request": r.name, "project": r.project}, user=u, after_commit=True)


@frappe.whitelist(methods=["POST"])
def decide(request: str, answer_id: str, answer: str, tokens: dict | str, option: str | None = None,
		reason: str | None = None, signature: dict | str | None = None, location: dict | str | None = None) -> dict:
	"""Approve or Return (§3.5 items 6-8). ``answer``: "approve" (a signature, and a Decision's option) or "return" (a
	reason). ``tokens``: the sheet's, unchanged. ``answer_id``: one per click; a repeat returns the first result."""
	user = answerer()
	tokens = frappe.parse_json(tokens) if isinstance(tokens, str) else tokens
	reason = cstr(reason).strip()[:NOTE_MAX]
	if answer not in ("approve", "return") or not isinstance(answer_id, str) or not ANSWER_ID.match(answer_id) \
			or not isinstance(tokens, dict):
		frappe.throw(_("This answer cannot be read. Reload the page and try again."))
	if answer == "return" and not reason:
		frappe.throw(_("Say why you are returning it"))
	if not read.readable(request):
		raise frappe.DoesNotExistError(_("Not found"))
	sign = _signature(signature, user) if answer == "approve" else None  # before the lock: the picture's re-encode
	out = log.retry_once(lambda: _decide(request, user, answer_id, answer, tokens, option, reason, sign, location))
	_publish(frappe._dict(name=request, project=frappe.db.get_value(log.REQUEST, request, "project")))
	return out


def _decide(request, user, answer_id, answer, tokens, option, reason, sign, location) -> dict:
	hashes = log.prehash(request)  # the file bytes, before the lock
	terms_ok = log.terms_agree(request, hashes)  # takes the subject, the project and the request, in that order
	r = frappe._dict(log.lock(frappe.db.get_value(log.REQUEST, request, "project"), request))  # held: the latest row
	first = [e for e in frappe.get_all(log.EVENT, filters={"request": r.name, "actor": user,
		"kind": ("in", ("approved", "returned"))}, fields=["name", "kind", "request", "actor", "canonical"])
		if json.loads(e.canonical)["body"].get("answer_id") == answer_id]
	if first:
		return _result(first[0])  # the same click again (M5)
	from construction_core.approvals.preflight import preflight  # here: preflight imports api, which this module does

	if [x for x in preflight(r.project) if x["key"] != "approver"]:  # an approver no longer named: NotApprover below
		frappe.throw(_(WORDS["ApprovalsClosed"]), ApprovalsClosed)
	if r.status != "Open":
		e = _last_state(r.name)
		if r.status in ("Approved", "Returned"):
			at = convert_utc_to_system_timezone(e.at_utc).strftime("%H:%M on %d %b %Y")
			frappe.throw(_(WORDS["AlreadyAnswered"]).format(_by(e), _(r.status.lower()), at), AlreadyAnswered)
		if r.status == "Voided":
			frappe.throw(_(WORDS["Voided"]).format(json.loads(e.canonical)["body"].get("reason") or _("no reason given")),
				Voided)
		frappe.throw(_(WORDS["Replaced"]), Replaced)
	if not approvers(r.project).get(user):
		frappe.throw(_(WORDS["NotApprover"]), NotApprover)
	if credentials.must_reset(user):
		frappe.throw(_(credentials.MUST_RESET), credentials.MustReset)
	agreed = agreement.accepted(r.project, user)
	if not agreed:
		frappe.throw(_(WORDS["NeedsAgreement"]), NeedsAgreement)
	data, sid = frappe._dict(frappe.session.data), frappe.session.sid
	if _step_due(data, sid):
		frappe.throw(_(WORDS["PasswordNeeded"]), PasswordNeeded)
	on = frappe.db.get_value(PROJECT, r.project, "cc_device_location")
	if tokens != _tokens(r, on):
		frappe.throw(_(WORDS["PageOutdated"]), PageOutdated)
	subject = frappe.get_doc(r.subject_doctype, r.subject_name)  # its row locked by terms_agree
	if not terms_ok or not subjects.allowed(subject):
		subjects.supersede(r, "The record left its allowed state" if terms_ok else "The terms changed")
		return {"state": "replaced", "request": r.name, "message": _(WORDS["Replaced"])}
	terms, lines = json.loads(r.snapshot)["terms"], agreement.lines(r)
	chosen = next((o for o in terms.get("options") or [] if o["key"] == option), None)
	if answer == "approve" and r.subject_doctype == subjects.DECISION and not chosen:
		frappe.throw(_("Choose one of the options"))
	body = _body(r, user, answer_id, answer, reason, agreed, data, sid, on,
		lines.get(chosen["key"] if chosen else "record", ""))
	if answer == "approve":
		if chosen:
			body.update({"option": chosen["key"], "option_sha256": canonical.sha256(canonical.text(chosen)),
				"option_label": chosen["label"], "option_cost": chosen["cost_difference"],
				"option_days": chosen["time_difference"]})
		png = sign.get("png")  # read, never popped: a lost race runs this again with the same sign
		body["signature"] = {**{k: v for k, v in sign.items() if k != "png"},
			"file": frozen.store(png, seal=_fernet().encrypt) if png else ""}
	kind, where = "approved" if answer == "approve" else "returned", _location(location, cint(on))
	name = log.append_event(r.project, kind, request=r.name, body=body, detail=_detail(where))
	from construction_core.approvals import receipts  # here: receipts imports this module

	receipts.queue(name)  # after the commit only: a lost race's rollback drops it, a repeated answer id never gets here
	api.answered(r, kind, user)  # P3-78 (§3.13): the staff bell "Client answered"
	state = json.loads(where)["state"] if where else ""
	if state in ("not_ticked", "denied"):  # a "no" is remembered for this person; a shared one forgets it
		frappe.defaults.set_user_default(LOCATION_NO, "1")
	elif state == "shared":
		frappe.defaults.clear_user_default(LOCATION_NO)
	if answer == "approve":
		from construction_core.approvals import routes  # here: routes imports api, which imports a lot

		routes.client_approved(r, subject)  # P3-82 (§14.3 item 5): the after-client steps, then a Decision is Decided
	elif r.subject_doctype == subjects.DECISION:
		subjects._needs_new(r, subject)
	return _result(frappe._dict(name=name, kind=kind, request=r.name, actor=user))


def _body(r, user, answer_id, answer, reason, agreed, data, sid, on, line) -> dict:
	"""The answer event's text (§4.1); the personal detail goes to Approval Evidence Detail, the event keeps only its
	commitment."""
	designation = next((e.seq for e in frappe.get_all(log.EVENT, filters={"project": r.project, "kind": "designation"},
		fields=["seq", "canonical"], order_by="seq desc") if json.loads(e.canonical)["body"]["user"] == user), 0)
	confirmation = next((e.seq for e in frappe.get_all(log.EVENT, filters={"project": r.project, "kind": "settings"},
		fields=["seq", "canonical"], order_by="seq desc") if json.loads(e.canonical)["body"].get("confirmation")), 0)
	return {"answer_id": answer_id, "answer": answer, "reason": reason, "terms_hash": r.terms_hash, "build": __version__,
		"who": {"user": user, "full_name": get_fullname(user), "email": _email(user), "kind": "client",
			"designation_seq": designation},
		"agreement": {"confirmation_seq": confirmation, "agreed_seq": agreed, "language": agreement.LANGUAGE,
			"versions": {"agreement": agreement.VERSION, "line": agreement.LINES_VERSION,
				"notice": agreement.NOTICE_VERSION if cint(on) else ""},
			"line_sha256": canonical.sha256(line), "location_switch": "1" if cint(on) else "0"},
		"session": {"sid_sha256": canonical.sha256(sid), "started": get_datetime(data.creation),
			"two_step": "1" if two_step.is_on(user) else "0",
			"password_step": "1" if frappe.cache.get_value(f"cc:approval:step_ok:{sid}") else "0"},
		"credentials": credentials.last_change(user)}
