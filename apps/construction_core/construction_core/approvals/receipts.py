"""The receipts of an answer (approvals design §3.6, §4.5; P3-78; threats T13, T22, T25).

- ``queue(event)``: once the transaction commits, a job on the short queue sends each receipt of an answer event
  (``approved`` or ``returned``) at once. ``decide`` calls it, and so does a staff-recorded approval, whose event body
  names the approver who gave it in ``signer`` (``decider_of``).
- **Per recipient** (T25). The approver who answered (the decider) gets the record, the chosen option, the cost and time,
  the answer and its reason, the time in the site's zone and in UTC, the chain position and fingerprint, their own
  signature as an attachment, their own network address and device, and the "This was not me" link (approvals.dispute),
  whose single-use token is kept only as its hash. Their receipt goes to every address the account has held (§4.5). The
  other approvers get the record, the answer, the decider's name, the time and the fingerprint: nothing personal.
- **Each mail is a chain event** (T22): ``receipt_sent`` (the recipients, Message-ID, the body's SHA-256, the outgoing
  mail account and its host, the token's hash on the decider's; the event's own time) or ``receipt_failed``, which
  alerts the managers on the bell. ``retry_due`` tries a failed one again every 5 minutes, RETRIES times in all; then
  staff ``resend``. Only the latest token of an answer works. The decider's own copy is ``my_copy``.
"""

import json
import secrets
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_fullname, get_system_timezone, get_url
from frappe.utils.data import convert_utc_to_system_timezone
from werkzeug.wrappers import Response

from construction_core.approvals import SANDBOX, agreement, api, canonical, credentials, log, read, subjects
from construction_core.approvals.answer import signature_picture
from construction_core.notifications import RECEIPT_FAILED, notify
from construction_core.onboarding import invites
from construction_core.onboarding.mail import _brand_args

ANSWERS = ("approved", "returned")
RETRIES = 3  # failed tries of one receipt before only staff resend it
LOST = timedelta(minutes=15)  # an answer this old with no receipt event: its job was never queued
FIELDS = ["name", "project", "request", "kind", "seq", "hash", "at_utc", "actor", "canonical"]
TEMPLATE = "templates/emails/cc_approval_receipt.html"
DISPUTE_PAGE = "/approval-dispute"


class NotSent(Exception):
	"""The mail has no Sent row: no outgoing account, muted or suspended mail, a refused address or an SMTP error."""


def queue(event: str) -> None:
	"""The answer event's receipts, sent once this transaction commits (§3.6). A rollback drops them; the job queue is
	asked only after the commit, so its outage never fails an answer (retry_due sends a receipt never queued)."""
	frappe.db.after_commit.add(lambda: _enqueue(event))


def _enqueue(event: str) -> None:
	try:
		frappe.enqueue(f"{__name__}._job", queue="short", answer=event)
	except Exception:
		frappe.log_error(title="construction_core: a receipt job could not be queued", message=f"answer {event}",
			defer_insert=True)


def _job(answer: str) -> None:
	frappe.set_user("Administrator")  # the site sends them: no receipt event names the client as its actor
	send(answer)


def decider_of(e) -> str:
	"""Who gave the answer: the client who answered, or the named signer of a staff-recorded approval, never the staff
	member who recorded it."""
	body = json.loads(e.canonical)["body"]
	return body.get("signer") or (body.get("who") or {}).get("user") or e.actor


def answer_of(request: str):
	"""A request's answer event (Open moves to one answer only), or None."""
	rows = frappe.get_all(log.EVENT, filters={"request": request, "kind": ("in", ANSWERS)}, fields=FIELDS,
		order_by="seq desc", limit=1)
	return rows[0] if rows else None


def _addresses(user) -> list[str]:
	"""The account's address and every one it had before a rename (§4.5: receipts follow a rename)."""
	return list(dict.fromkeys([api._email(user), *(b["address"] for b in credentials._bodies(user)
		if b["change"] == "rename")]))


def when(at_utc) -> str:
	zone = get_system_timezone().rsplit("/", 1)[-1].replace("_", " ")
	return _("{0}, {1} time ({2} UTC)").format(f"{convert_utc_to_system_timezone(at_utc):%H:%M on %d %b %Y}", zone,
		f"{at_utc:%H:%M on %d %b %Y}")


def what(r) -> str:
	"""The record, title first and reference second (§5)."""
	terms = json.loads(r.snapshot)["terms"]
	return f'“{r.subject_title or terms.get("title") or ""}” ({terms.get("number") or r.subject_name})'


def _facts(e, r, body, decider) -> tuple[list, list]:
	"""The decider's own lines (label, value) and attachments: never in anyone else's receipt (T25)."""
	terms = json.loads(r.snapshot)["terms"]
	option = next((o for o in terms.get("options") or [] if o["key"] == body.get("option")), None)
	facts = [(_("Your choice"), option["label"])] if option else []
	if option:
		facts.append((_("Cost and time"), agreement._change(terms["currency"], option["cost_difference"],
			option["time_difference"])))
	elif r.subject_doctype == subjects.VO:
		facts.append((_("Cost and time"), agreement._change(terms["currency"], terms["total"], terms["days"])))
	elif r.subject_doctype != subjects.DECISION:
		facts.append((_("Revision"), str(terms.get("revision") or "-")))
	if body.get("reason"):
		facts.append((_("Your reason"), body["reason"]))
	facts.append((_("When"), when(e.at_utc)))
	sign, files = body.get("signature") or {}, []
	picture = signature_picture(sign["file"]) if sign.get("file") else None
	if picture:
		files.append({"fname": "signature.png", "fcontent": picture})
		facts.append((_("Signature"), _("drawn; the picture is attached to your receipt email")))
	elif sign.get("typed_name"):
		facts.append((_("Signature"), _("typed as “{0}”").format(sign["typed_name"])))
	if e.actor == decider:  # a staff-recorded approval's evidence detail is the recorder's, never the signer's
		d = frappe.db.get_value(log.DETAIL, {"event": e.name}, ["network_address", "browser", "system"], as_dict=True)
		if d and d.network_address:
			device = " on ".join(x for x in (d.browser, d.system) if x)
			facts.append((_("Sent from"), _("network address {0}").format(d.network_address)
				+ (f", {device}" if device else "")))
	elif body.get("label"):  # its method, recorder and day (§3.9); the event's actor is the manager who confirmed it
		facts.append((_("How it was given"), body["label"]))
	else:
		facts.append((_("Recorded by"), get_fullname(body.get("recorded_by") or e.actor)))
	return facts, files


def _grouped(code: str) -> str:
	"""The full code as the receipt draws it: the fingerprint's 8 characters, then groups of 4, so a phone wraps it at a space."""
	return " ".join([code[:8], *(code[i : i + 4] for i in range(8, len(code), 4))])


def receipt(e, r, decider, mine: bool, token: str | None = None) -> tuple[str, str, list]:
	"""(subject, body, attachments) of one recipient's receipt: the decider's whole (``mine``), else nothing personal."""
	body, verb = json.loads(e.canonical)["body"], _("approved") if e.kind == "approved" else _("returned")
	project = frappe.db.get_value(api.PROJECT, r.project, "project_name")
	facts, files = _facts(e, r, body, decider) if mine else ([], [])
	html = frappe.render_template(TEMPLATE, {**_brand_args(), "mine": mine, "verb": verb, "what": what(r),
		"project": project, "name": get_fullname(decider), "when": when(e.at_utc), "facts": facts, "seq": e.seq,
		"fingerprint": e.hash[:8], "code": _grouped(e.hash), "link": token and get_url(f"{DISPUTE_PAGE}#t={token}"),
		"attached": [(f["fname"], f"{max(1, round(len(f['fcontent']) / 1000))} KB") for f in files] if token else []})  # a downloaded copy has no attachment
	subject = _("Your receipt: you {0} {1}").format(verb, what(r)) if mine else \
		f"{get_fullname(decider)} {verb} {what(r)}"
	return subject, html, files


def send(answer: str, users: list[str] | None = None) -> dict:
	"""Send the answer event's receipts now, each recorded in the chain: to the decider and the project's other
	confirmed approvers, or to ``users`` only (a retry). {user: "sent" | "failed"}."""
	e = frappe.db.get_value(log.EVENT, answer, FIELDS, as_dict=True) if isinstance(answer, str) else None
	if not e or e.kind not in ANSWERS:
		raise frappe.DoesNotExistError(_("Not found"))
	r = frappe.get_doc(log.REQUEST, e.request)
	decider, out = decider_of(e), {}
	for user in users or [decider, *(u for u, ok in api.approvers(r.project).items() if ok and u != decider)]:
		mine = user == decider
		token = secrets.token_urlsafe(32) if mine else None
		subject, html, files = receipt(e, r, decider, mine, token)
		record = {"answer": e.name, "user": user, "role": "decider" if mine else "approver",
			"to": _addresses(user) if mine else [api._email(user)]}
		try:
			mail = _deliver(record["to"], subject, html, files)
		except Exception as error:
			log.append_event(r.project, "receipt_failed", request=r.name, body={**record, "error": type(error).__name__})
			notify(invites._managers(frappe.get_doc(api.PROJECT, r.project)), RECEIPT_FAILED, r, coalesce=True)
			out[user] = "failed"
			continue
		log.append_event(r.project, "receipt_sent", request=r.name, body={**record, **mail,
			"body_sha256": canonical.sha256(html), **({"token_sha256": canonical.sha256(token)} if token else {})})
		out[user] = "sent"
	return out


def _deliver(to: list[str], subject: str, html: str, attachments: list) -> dict:
	"""One receipt sent now: its Message-ID and outgoing account and host, read back from its Email Queue row; else
	NotSent. This module owns the retries (retry_due), so a row that did not go is redacted (it holds the token and the
	signature) and set to Error, which Frappe's own queue never sends; Frappe redacts a sent one."""
	q = frappe.sendmail(recipients=to, subject=subject, message=html, attachments=attachments, add_unsubscribe_link=0,
		redact_message_after_send=True)  # queued, not sent: sent below, so a failure leaves its row in our hands
	if not q:
		raise NotSent("no recipient left")
	try:
		q.send()
	except Exception:
		pass  # its row says what happened
	row = frappe.db.get_value("Email Queue", q.name, ["status", "message_id", "email_account"], as_dict=True)
	if row.status != "Sent":
		# shortcut: Frappe's flush could pick the row between its own commit and this one (milliseconds); its link
		# would not work (no receipt_sent names its token). Upgrade by sending through our own SMTP call if seen.
		frappe.get_doc("Email Queue", q.name).redact_message()
		frappe.db.set_value("Email Queue", q.name, "status", "Error", update_modified=False)
		raise NotSent(row.status)
	host = frappe.db.get_value("Email Account", row.email_account, "smtp_server") if row.email_account \
		else frappe.conf.get("mail_server")
	return {"message_id": row.message_id or "", "email_account": row.email_account or "", "host": host or ""}


def retry_due() -> None:
	"""Every 5 minutes (hooks): each receipt whose latest try failed, while it failed fewer than RETRIES times; and an
	answer of more than LOST ago with no receipt event at all (its job was never queued)."""
	failed = {}
	# shortcut: reads every receipt event of the site; index them by answer once there are thousands
	for e in frappe.get_all(log.EVENT, filters={"kind": ("in", ("receipt_sent", "receipt_failed"))},
			fields=["kind", "canonical"], order_by="project asc, seq asc"):
		b = json.loads(e.canonical)["body"]
		key = (b["answer"], b["user"])
		failed[key] = 0 if e.kind == "receipt_sent" else failed.get(key, 0) + 1
	for (answer, user), times in failed.items():
		if 0 < times < RETRIES:
			send(answer, [user])
	seen = {answer for answer, _user in failed}
	for answer in frappe.get_all(log.EVENT, filters={"kind": ("in", ANSWERS),
			"at_utc": ("<", log._now().replace(tzinfo=None) - LOST)}, pluck="name"):
		if answer not in seen:
			send(answer)


@frappe.whitelist(methods=["POST"])
def resend(request: str) -> dict:
	"""Staff send an answer's receipts again (§3.6): a manager of the project (manage_clients). The decider's new
	receipt carries a new link, and only the latest one works."""
	r = read.readable(request)
	e = answer_of(request) if r else None
	if not e:
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.has_permission(api.PROJECT, "manage_clients", doc=frappe.get_doc(api.PROJECT, r.project), throw=True)
	out = send(e.name)
	return {state: [get_fullname(u) for u, s in out.items() if s == state] for state in ("sent", "failed")}


@frappe.whitelist(methods=["GET"])
def my_copy(request: str):
	""""Download my copy" (§3.6): the decider's own receipt as a file, after the request's read rule; anyone else gets
	"Not found". It carries no link, so it mints no token, and it writes nothing."""
	r = read.readable(request)
	e = answer_of(request) if r else None
	if not e or decider_of(e) != frappe.session.user:
		raise frappe.DoesNotExistError(_("Not found"))
	_subject, html, _files = receipt(e, r, frappe.session.user, True)
	return Response(html, status=200, content_type="text/html; charset=utf-8", headers={
		"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff",
		"Cross-Origin-Resource-Policy": "same-origin", "Content-Security-Policy": SANDBOX,
		"Content-Disposition": f"attachment; filename=receipt-{r.name}.html"})
