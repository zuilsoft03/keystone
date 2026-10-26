"""P3-53 (firm set-up W3, design §4 and §6 T2–T4): the site's outgoing mail from the Mail panel.

It is Frappe's default outgoing Email Account, the same record as Desk → Email Account (RUNBOOK §4a), so mail keeps one
code path. System Managers only, the same right as Desk (T2); who changed it last, and when, is the account's own
modified_by and modified. The server field cannot point inside the stack (T3). The password lives only in the account's
password field: no answer carries it, and every error has it removed (T4). A test mail carries a 6-digit code to the
System Manager's own address; the typed code proves that mail leaves the server and arrives (W3).
"""

import base64
import binascii
import hashlib
import hmac
import ipaddress
import re
import secrets
import socket
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.password import get_decrypted_password, get_encryption_key

SECURITY = ("ssl", "starttls", "none")
PORTS = (25, 465, 587, 2525)  # the SMTP ports; any other would let the field probe internal services (T3)
# The stack's own services (dev/docker-compose.yml, deploy/compose.yml); a dotless name is refused anyway (T3).
STACK_NAMES = {"db", "redis-cache", "redis-queue", "configurator", "backend", "websocket", "queue-short", "queue-long",
	"queue-thumbs", "renderer", "scheduler", "frontend", "backup", "documentserver", "clamav-update", "clamav", "proxy",
	"mailpit", "office", "scan", "localhost"}
CODE_MINUTES, CODE_TRIES, CODES_PER_HOUR = 15, 5, 10
CONFIRMED_KEY = "cc_mail_confirmed"  # a __global default (never in any boot): the account version the code proved
B64 = re.compile(r"[A-Za-z0-9+/=]{8,}")


def _mark(step: str, state: str) -> None:
	from construction_core.accounts.setup import mark  # S1's module; imported when used

	mark(step, state)


def _account():
	name = frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1})
	return frappe.get_doc("Email Account", name) if name else None


def _login(acc) -> str:
	return "" if acc.no_smtp_authentication else (acc.login_id if acc.login_id_is_different else acc.email_id) or ""


def _version(acc) -> str:
	return f"{acc.name}|{acc.modified}"


@frappe.whitelist()
def get() -> dict:
	frappe.only_for("System Manager")
	acc = _account()
	if not acc:
		return {"server": "", "port": 587, "security": "starttls", "login": "", "from_address": "", "has_password": False,
			"last_error": "", "changed_by": "", "changed_on": None, "confirmed": False}
	security = "ssl" if acc.use_ssl_for_outgoing else "starttls" if acc.use_tls else "none"
	stored = get_decrypted_password("Email Account", acc.name, "password", raise_exception=False)
	return {"server": acc.smtp_server or "", "port": cint(acc.smtp_port), "security": security, "login": _login(acc),
		"from_address": acc.email_id or "", "has_password": bool(stored),
		"last_error": frappe.cache.get_value(_error_key()) or "", "changed_by": acc.modified_by, "changed_on": acc.modified,
		"confirmed": frappe.db.get_global(CONFIRMED_KEY) == _version(acc)}


@frappe.whitelist(methods=["POST"])
def save(server=None, port=None, security=None, login=None, password=None, from_address=None) -> dict:
	frappe.only_for("System Manager")
	server = _check_server(server, port)
	if security not in SECURITY:
		frappe.throw(_("Choose the security: SSL, STARTTLS or none."))
	sender = (from_address or "").strip().lower() if isinstance(from_address, str) else ""
	if not sender or frappe.utils.validate_email_address(sender, throw=False) != sender:
		frappe.throw(_("Enter the address the mail is sent from, like projects@example.com."))
	login = (login or "").strip() if isinstance(login, str) else ""
	if password is not None and not isinstance(password, str):
		frappe.throw(_("The password must be text."))

	acc = _account() or frappe.new_doc("Email Account")
	if not acc.is_new() and not password and (server != (acc.smtp_server or "").lower()
			or login.lower() != _login(acc).lower()):
		acc.password = None  # the stored password is never sent to a server or a login it was not typed for (T4)
	if acc.is_new():
		acc.update({"email_account_name": sender, "enable_outgoing": 1, "default_outgoing": 1, "enable_incoming": 0})
	acc.update({"smtp_server": server, "smtp_port": cint(port), "email_id": sender,
		"use_ssl_for_outgoing": cint(security == "ssl"), "use_tls": cint(security == "starttls"),
		"no_smtp_authentication": cint(not login), "awaiting_password": 0,
		"login_id_is_different": cint(bool(login) and login.lower() != sender), "login_id": login})
	if login and password:
		acc.password = password
	secret = password or (get_decrypted_password("Email Account", acc.name, "password", raise_exception=False)
		if not acc.is_new() else None)
	# Frappe signs in to the server on save (not in tests); its errors are passed on without the password (T4).
	error = _quietly(lambda: acc.save(ignore_permissions=True), secret)
	if error:
		frappe.throw(_("The mail server refused the settings: {0}").format(error))
	frappe.cache.delete_value(_error_key())
	if hasattr(frappe.local, "outgoing_email_account"):
		del frappe.local.outgoing_email_account  # the request's cached account (cache_email_account)
	return get()


@frappe.whitelist(methods=["POST"])
def test(to: str | None = None) -> dict:
	"""``to``: the address the code goes to, when the System Manager has none of their own yet (Administrator in the
	wizard, before W4 makes the owner's account); else their own."""
	frappe.only_for("System Manager")
	acc = _account()
	if not acc:
		frappe.throw(_("Save the mail settings first."))
	_check_server(acc.smtp_server, acc.smtp_port)  # an account made in Desk is checked too (T3)
	to = (to or "").strip() or frappe.db.get_value("User", frappe.session.user, "email")
	if not to or to == "admin@example.com" or re.search(r"[,;\r\n]", to) or not frappe.utils.validate_email_address(to):
		# Frappe's placeholder for Administrator: the code would go nowhere
		frappe.throw(_("Type the address the test mail should go to."))
	key = frappe.cache.make_key(f"cc_mail_codes:{frappe.session.user}")
	sent = frappe.cache.incrby(key, 1)
	if sent == 1 or frappe.cache.ttl(key) < 0:
		frappe.cache.expire(key, 3600)
	if sent > CODES_PER_HOUR:
		frappe.throw(_("Too many test mails. Try again in an hour."))

	code = f"{secrets.randbelow(10**6):06d}"
	msg = EmailMessage()
	company = _company()
	msg["Subject"] = _("{0}: your mail test code").format(company)
	msg["From"], msg["To"], msg["Message-ID"] = formataddr((company, acc.email_id)), to, make_msgid()
	msg.set_content(_("Your mail test code is {0}. Type it in the set-up page within {1} minutes.").format(code,
		CODE_MINUTES))
	secret = get_decrypted_password("Email Account", acc.name, "password", raise_exception=False)

	def send():
		acc.flags.validate_smtp_connection = True  # Frappe's 15-second timeout, as on save
		acc.get_smtp_server().session.sendmail(acc.email_id, [to], msg.as_string())

	# Sent here, not through the Email Queue: the queue would keep the code in plain text, and hide the server's reply.
	error = _quietly(send, secret)
	if error:
		frappe.cache.set_value(_error_key(), error, expires_in_sec=86400)
		return {"sent": False, "error": error}
	frappe.cache.delete_value(_error_key())
	frappe.cache.set_value(_code_key(), {"hash": _hmac(_version(acc), code), "tries": 0}, expires_in_sec=CODE_MINUTES * 60)
	return {"sent": True}


@frappe.whitelist(methods=["POST"])
def confirm(code=None) -> dict:
	frappe.only_for("System Manager")
	acc = _account()
	held = frappe.cache.get_value(_code_key())
	if not acc or not held:
		return {"state": "expired"}
	digits = re.sub(r"\D", "", code if isinstance(code, str) else "")[:6]
	# The account's version is in the hash: a change after the test makes its code stale.
	if not hmac.compare_digest(_hmac(_version(acc), digits), held["hash"]):
		tries = cint(held["tries"]) + 1
		if tries >= CODE_TRIES:
			frappe.cache.delete_value(_code_key())
			return {"state": "locked"}
		ttl = frappe.cache.ttl(frappe.cache.make_key(_code_key()))
		frappe.cache.set_value(_code_key(), {**held, "tries": tries}, expires_in_sec=max(1, ttl))
		return {"state": "wrong", "left": CODE_TRIES - tries}
	frappe.cache.delete_value(_code_key())
	frappe.db.set_global(CONFIRMED_KEY, _version(acc))
	_mark("W3", "done")
	return {"state": "confirmed"}


def _check_server(server, port) -> str:
	"""T3: a mail server outside the stack and off the loopback and link-local ranges, on an SMTP port."""
	host = (server or "").strip().lower().rstrip(".") if isinstance(server, str) else ""
	host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
	if not host or len(host) > 253:
		frappe.throw(_("Enter the mail server, like smtp.company.com."))
	if cint(port) not in PORTS or str(port).strip() != str(cint(port)):
		frappe.throw(_("Use a mail port: 25, 465, 587 or 2525."))
	if host in STACK_NAMES or host.endswith(".localhost") or not _is_ip(host) and "." not in host:
		frappe.throw(_("That is not a mail server name. Use its full name, like smtp.company.com."))
	try:
		found = {ai[4][0] for ai in socket.getaddrinfo(host, cint(port), proto=socket.IPPROTO_TCP)}
	except (OSError, UnicodeError):
		frappe.throw(_("The mail server {0} was not found.").format(host))
	# shortcut: checked at save and at test; a name that changes its address in between is not caught (DNS rebinding).
	for address in found:
		ip = ipaddress.ip_address(address.split("%")[0])
		ip = getattr(ip, "ipv4_mapped", None) or ip
		if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
			frappe.throw(_("That address is inside this server. Use the mail provider's server."))
	return host


def _is_ip(host: str) -> bool:
	try:
		ipaddress.ip_address(host)
		return True
	except ValueError:
		return False


def _quietly(work, secret) -> str:
	"""Run work; on failure, its error (and Frappe's messages) without the password. "" when it succeeds."""
	log = frappe.local.message_log
	kept = len(log)
	try:
		work()
		return ""
	except Exception as e:
		return _scrub(str(e), secret)[:500] or type(e).__name__  # Frappe's throw puts its message on e
	finally:
		del log[kept:]  # Frappe's msgprint copies would reach the browser as _server_messages (T4)


def _scrub(text: str, secret: str | None) -> str:
	"""Remove the password, and any base64 token holding it (AUTH LOGIN and AUTH PLAIN send it so), from text."""
	text = text or ""
	if secret:
		# as is, as a bytes repr shows it (Frappe quotes the traceback's last line), and HTML-escaped
		for form in sorted({secret, repr(secret.encode())[2:-1], frappe.utils.escape_html(secret)}, key=len, reverse=True):
			text = text.replace(form, "****")
	text = frappe.utils.strip_html(text).strip()
	if not secret:
		return text

	def hide(m):
		try:
			raw = base64.b64decode(m.group(0) + "=" * (-len(m.group(0)) % 4), validate=False)
		except (binascii.Error, ValueError):
			return m.group(0)
		return "****" if secret.encode() in raw else m.group(0)

	return B64.sub(hide, text)


def _hmac(version: str, code: str) -> str:
	return hmac.new(get_encryption_key().encode(), f"{version}|{frappe.session.user}|{code}".encode(),
		hashlib.sha256).hexdigest()


def _company() -> str:
	from construction_core.onboarding.mail import brand_name

	return brand_name()


def _code_key() -> str:
	return f"cc_mail_code:{frappe.session.user}"


def _error_key() -> str:
	return "cc_mail_last_error"
