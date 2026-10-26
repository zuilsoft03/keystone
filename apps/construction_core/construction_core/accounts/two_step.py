"""P3-20 (R-13; D-190, D-227): two-step sign-in, each person's own choice.

Frappe asks for a code at sign-in when the site switch is on and one of the person's roles carries the per-role flag.
Only ROLE carries it, and it has no desk access, so a client who turns it on stays a client and nobody is affected until
they opt in. The method is an authenticator app (Frappe's "OTP App"); the secret is Frappe's own (`<user>_otpsecret`,
encrypted in the database).

Turning it on happens here, not through Frappe's first-sign-in email (D-227): `start` takes the password and returns a
new secret as a QR code and a key; only `confirm` with a current code from the app adds the role and marks Frappe's
setup done, so a setup that did not work locks nobody out. `turn_off` needs the password and a current code, so a
stolen session alone cannot remove it. Wrong passwords and codes count against TRIES an hour, kept in the database
under a lock on the person's User; a code is used once. Every change and refusal is a Comment on the User.
`reset_for` is the System Manager's switch-off for a lost phone (the People page, P3-21); it is not whitelisted.

After the review (D-229): the role is added only through `confirm` (`guard_role`), so Frappe's setup by email never
runs; `confirm` takes only the current code, as Frappe's sign-in does; a change ends the person's other sessions and
OAuth tokens and mails them a notice; the try count and the last used code are read with locking reads; and Frappe's
dynamic OAuth client registration is off, since a bearer token never meets the second step.

The owner's change (D-230, D-231): it stays each person's choice unless a System Manager requires it of the team or of
everyone (`set_requirement`); then those roles carry the flag too, and a person it applies to cannot turn it off.
"""

import time

import frappe
import pyotp
from frappe import _
from frappe.cache_manager import clear_defaults_cache
from frappe.twofactor import PARENT_FOR_DEFAULTS, clear_default, get_otpsecret_for_, get_qr_svg_code, set_default
from frappe.utils import cint, escape_html
from frappe.utils.password import check_password

ROLE = "Two-Step Sign-In"
TRIES, WINDOW_SECONDS, SETUP_SECONDS = 5, 3600, 600
REQUIRED_KEY = "cc_two_step_required"  # nobody (each person chooses), team or everyone (D-231)
TEAM = ("Construction Manager", "Construction Staff", "System Manager")
SCOPES = {"nobody": (), "team": TEAM, "everyone": (*TEAM, "Construction Client")}


def requirement() -> str:
	scope = frappe.db.get_default(REQUIRED_KEY)
	return scope if scope in SCOPES else "nobody"


def required_roles() -> set[str]:
	return {r for r in SCOPES[requirement()] if frappe.db.exists("Role", r)}


def required_for(user: str) -> bool:
	roles = required_roles()
	return bool(roles and frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": ("in", list(roles))}))


def setup():
	"""The role, the site switch with the authenticator app, and no other role flagged (install, patch, migrate)."""
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0, "two_factor_auth": 1}).insert(
			ignore_permissions=True)
	frappe.db.set_value("Role", ROLE, {"desk_access": 0, "two_factor_auth": 1}, update_modified=False)
	flagged = {ROLE} | required_roles()
	for role in frappe.get_all("Role", filters={"two_factor_auth": 1}, pluck="name"):
		if role not in flagged:
			frappe.db.set_value("Role", role, "two_factor_auth", 0, update_modified=False)
	for role in flagged:
		frappe.db.set_value("Role", role, "two_factor_auth", 1, update_modified=False)
	frappe.db.set_single_value("System Settings", "enable_two_factor_auth", 1)
	frappe.db.set_single_value("System Settings", "two_factor_method", "OTP App")
	if frappe.db.table_exists("OAuth Settings"):
		frappe.db.set_single_value("OAuth Settings", "enable_dynamic_client_registration", 0)  # D-229
	frappe.clear_cache()


def deviations() -> list[str]:
	"""What differs from setup(); the tests use it, and P3-10's go-live check."""
	out = []
	if not cint(frappe.db.get_single_value("System Settings", "enable_two_factor_auth")):
		out.append("System Settings.enable_two_factor_auth")
	if frappe.db.get_single_value("System Settings", "two_factor_method") != "OTP App":
		out.append("System Settings.two_factor_method")
	flagged = set(frappe.get_all("Role", filters={"two_factor_auth": 1}, pluck="name"))
	if flagged != {ROLE} | required_roles():
		out.append(f"Role.two_factor_auth: {sorted(flagged)}")
	if cint(frappe.db.get_value("Role", ROLE, "desk_access")):
		out.append(f"Role {ROLE}.desk_access")
	if frappe.db.table_exists("OAuth Settings") and \
			cint(frappe.db.get_single_value("OAuth Settings", "enable_dynamic_client_registration")):
		out.append("OAuth Settings.enable_dynamic_client_registration")
	return out


def guard_role(doc, method=None):
	"""User validate: the role is added only by `confirm`, after a code from the app, so Frappe's setup by email never
	runs for it (D-229). A System Manager may still take it away (the same as reset_for, without the record)."""
	before = doc.get_doc_before_save()
	had = ROLE in {r.role for r in (before.get("roles") if before else [])}
	if not had and ROLE in {r.role for r in doc.get("roles") or []} and not doc.flags.cc_two_step:
		frappe.throw(_("Two-step sign-in is turned on by the person, from their account menu."), frappe.PermissionError)


def is_on(user: str) -> bool:
	return bool(frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": ROLE}))


def _record(user: str, text: str):
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "User", "reference_name": user,
		"content": text}).insert(ignore_permissions=True)  # the person's own record; written by this module only


def _me() -> str:
	user = frappe.session.user
	if user == "Guest":
		raise frappe.PermissionError(_("Sign in first."))
	frappe.db.get_value("User", user, "name", for_update=True)  # one change of this person's sign-in at a time
	return user


def _read(key: str) -> str | None:
	"""A two-step value, read with a lock: the latest committed, never a cached or snapshot copy (D-229)."""
	row = frappe.db.sql("select defvalue from `tabDefaultValue` where parent = %s and defkey = %s for update",
		(PARENT_FOR_DEFAULTS, key))
	return row[0][0] if row else None


def _write(key: str, value):
	set_default(key, value)
	frappe.db.after_commit.add(lambda: clear_defaults_cache(PARENT_FOR_DEFAULTS))  # no stale copy outlives the commit


def _tries_left(user: str) -> int:
	raw = _read(f"{user}_cc_2step_tries") or ""
	count, _sep, since = raw.partition("|")
	if not since or (time.time() - float(since)) > WINDOW_SECONDS:
		return TRIES
	return max(0, TRIES - cint(count))


def _refuse(user: str, why: str, state: str) -> dict:
	"""Count a wrong password or code against the hour's tries, record it, and answer; never raised, so it is kept."""
	raw = _read(f"{user}_cc_2step_tries") or ""
	count, _sep, since = raw.partition("|")
	now = time.time()
	if not since or (now - float(since)) > WINDOW_SECONDS:
		count, since = 0, now
	_write(f"{user}_cc_2step_tries", f"{cint(count) + 1}|{since}")
	_record(user, f"Two-step sign-in: refused ({why})")
	return {"state": state, "left": _tries_left(user)}


def _password_ok(user: str, password) -> bool:
	try:
		check_password(user, password if isinstance(password, str) else "", delete_tracker_cache=False)
		return True
	except frappe.AuthenticationError:
		return False


def _code_ok(user: str, secret: str, code, steps=(-1, 0, 1)) -> bool:
	"""A current code from the app (by default one step either side for a slow clock), never one already used."""
	digits = "".join(ch for ch in (code if isinstance(code, str) else "") if ch.isdigit())
	step = int(time.time()) // 30  # the phone's clock is UTC time; never the site's local time (now_datetime)
	totp = pyotp.TOTP(secret)
	last = cint(_read(f"{user}_cc_2step_last"))
	for at in (step + s for s in steps):
		if at > last and len(digits) == 6 and pyotp.utils.strings_equal(digits, totp.generate_otp(at)):
			_write(f"{user}_cc_2step_last", at)
			return True
	return False


def _forget_secret(user: str):
	for key in ("_otpsecret", "_otplogin", "_cc_2step_last"):
		clear_default(user + key)
	frappe.db.after_commit.add(lambda: clear_defaults_cache(PARENT_FOR_DEFAULTS))


def _after_change(user: str, what: str, keep_current: bool):
	"""A change ends the person's other sessions and their OAuth tokens (a token never meets the second step), and
	tells them by mail when the site can send it (D-229)."""
	table = frappe.qb.DocType("Sessions")
	query = frappe.qb.from_(table).select(table.sid).where(table.user == user)
	if keep_current and frappe.session.sid:
		query = query.where(table.sid != frappe.session.sid)
	sids = [r[0] for r in query.run()]
	if sids:
		frappe.db.delete("Sessions", {"sid": ("in", sids)})
		frappe.db.after_commit.add(lambda: [frappe.cache.hdel("session", sid) for sid in sids])
	if frappe.db.table_exists("OAuth Bearer Token"):
		frappe.db.set_value("OAuth Bearer Token", {"user": user, "status": "Active"}, "status", "Revoked")
	from construction_core.approvals import credentials
	from construction_core.onboarding import mail

	credentials.changed(user, "two_step")  # P3-78 (§4.5): a client's; reset_for is a change by someone else

	email = frappe.db.get_value("User", user, "email")
	if email and mail.mail_ready():
		try:
			text = _("Two-step sign-in was {0} for your account. If this was not you, contact your System "
				"Manager now.").format(what)
			frappe.sendmail(recipients=[email], subject=_("Two-step sign-in was {0}").format(what), now=True,
				message=f"<p>{escape_html(text)}</p>" + mail.credit_html())  # the credit ends every mail (D-402)
		except Exception:
			frappe.log_error(title="construction_core: a two-step notice could not be queued", message=user,
				defer_insert=True)


def _set_role(user: str, on: bool):
	doc = frappe.get_doc("User", user)
	others = {r.role for r in doc.roles if r.role != ROLE}
	roles = [r for r in doc.roles if r.role != ROLE]
	doc.set("roles", roles)
	if on:
		doc.append("roles", {"role": ROLE})
	doc.flags.cc_two_step = True
	doc.save(ignore_permissions=True)  # only ROLE is added or removed (no desk access, no other right)
	after = set(frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, pluck="role")) - {ROLE}
	if is_on(user) != on or after != others:  # roles read back: nothing but ROLE changed (P3-21 review 1)
		frappe.throw(_("Two-step sign-in could not be changed."))  # roles read back after the save


def _set_up(user: str) -> bool:
	return bool(frappe.db.get_value("DefaultValue", {"parent": PARENT_FOR_DEFAULTS, "defkey": user + "_otplogin"},
		"defvalue"))


@frappe.whitelist(methods=["GET"])
def status() -> dict:
	user = frappe.session.user
	if user == "Guest":
		raise frappe.PermissionError(_("Sign in first."))
	required = required_for(user)
	return {"on": is_on(user) or (required and _set_up(user)), "required": required, "set_up": _set_up(user),
		"site_on": not deviations(), "tries_left": _tries_left(user)}


@frappe.whitelist(methods=["GET"])
def requirement_status() -> dict:
	"""For the People page: who must use it, and whether the site can send the setup email (D-231)."""
	frappe.only_for("System Manager")
	from construction_core.onboarding import mail

	roles = list(required_roles())
	people = frappe.get_all("Has Role", filters={"parenttype": "User", "role": ("in", roles or [""])},
		pluck="parent", distinct=True)
	enabled = set(frappe.get_all("User", filters={"name": ("in", people or [""]), "enabled": 1}, pluck="name"))
	# Who must use it and has not set it up: their next sign-in needs the setup email (P3-20 delta audit S2).
	waiting = sorted(u for u in enabled if u != "Guest" and not _set_up(u))
	return {"requirement": requirement(), "scopes": list(SCOPES), "mail_ready": mail.mail_ready(),
		"not_set_up": waiting}


@frappe.whitelist(methods=["POST"])
def set_requirement(scope=None) -> dict:
	"""A System Manager requires it of the team or of everyone, or leaves it to each person (D-230, D-231)."""
	frappe.only_for("System Manager")
	if scope not in SCOPES:
		frappe.throw(_("Choose nobody, team or everyone."))
	from construction_core.onboarding import mail

	if scope != "nobody" and not mail.mail_ready():
		frappe.throw(_("Set up outgoing email first: whoever has not set up two-step sign-in gets its setup by email."))
	if scope != "nobody" and not _set_up(frappe.session.user):
		frappe.throw(_("Turn on two-step sign-in for your own account first, from the account menu."))  # delta S1
	before = requirement()
	frappe.db.set_default(REQUIRED_KEY, scope)
	setup()
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "System Settings",
		"reference_name": "System Settings",
		"content": f"Two-step sign-in required of: {scope} (was {before}), by {frappe.session.user}"}).insert(
		ignore_permissions=True)
	return {"requirement": requirement()}


@frappe.whitelist(methods=["POST"])
def start(password=None) -> dict:
	"""Step 1 of turning it on: the password, then a new secret to scan. Nothing changes for sign-in yet."""
	user = _me()
	if deviations():
		return {"state": "unavailable"}
	if is_on(user) or (required_for(user) and _set_up(user)):
		return {"state": "already_on"}
	if not _tries_left(user):
		return {"state": "locked"}
	if not _password_ok(user, password):
		return _refuse(user, "a wrong password while turning it on", "wrong_password")
	_forget_secret(user)
	secret = get_otpsecret_for_(user)  # a new one, encrypted in the database by Frappe
	try:
		qr, key = _scan(user, secret)
	except Exception:
		frappe.log_error(title="construction_core: two-step setup failed", message="details withheld (a new secret)",
			defer_insert=True)  # an error snapshot would keep the secret (P3-20 audit S1)
		raise frappe.ValidationError(_("Two-step sign-in could not be set up. Please try again.")) from None
	frappe.cache.set_value(f"cc:2step:setup:{user}", 1, expires_in_sec=SETUP_SECONDS)
	return {"state": "scan", "qr": qr, "key": key, "minutes": SETUP_SECONDS // 60}


def _scan(user: str, secret: str) -> tuple[str, str]:
	issuer = frappe.db.get_single_value("System Settings", "otp_issuer_name") or frappe.local.site
	svg = get_qr_svg_code(pyotp.TOTP(secret).provisioning_uri(frappe.db.get_value("User", user, "email") or user,
		issuer_name=issuer))
	return ("data:image/svg+xml;base64," + (svg.decode() if isinstance(svg, bytes) else svg),
		" ".join(secret[i:i + 4] for i in range(0, len(secret), 4)))


@frappe.whitelist(methods=["POST"])
def confirm(code=None) -> dict:
	"""Step 2: a current code from the app proves it works; only then is the role added."""
	user = _me()
	if is_on(user):
		return {"state": "already_on"}
	if not frappe.cache.get_value(f"cc:2step:setup:{user}"):
		return {"state": "start_again"}
	if not _tries_left(user):
		return {"state": "locked"}
	secret = get_otpsecret_for_(user)
	if not _code_ok(user, secret, code, steps=(0,)):  # only the current code, as Frappe's sign-in takes (D-229)
		return _refuse(user, "a wrong code while turning it on", "wrong_code")
	_set_role(user, True)
	_write(user + "_otplogin", 1)  # Frappe's own setup is done: sign-in asks the app's code, no email
	frappe.cache.delete_value(f"cc:2step:setup:{user}")
	clear_default(f"{user}_cc_2step_tries")
	_record(user, "Two-step sign-in turned on")
	_after_change(user, _("turned on"), keep_current=True)
	return {"state": "on"}


@frappe.whitelist(methods=["POST"])
def turn_off(password=None, code=None) -> dict:
	"""The password and a current code: a session alone, stolen or left open, cannot remove it."""
	user = _me()
	if required_for(user):
		return {"state": "required"}  # a System Manager requires it of this person (D-231)
	if not is_on(user):
		return {"state": "already_off"}
	if not _tries_left(user):
		return {"state": "locked"}
	if not _password_ok(user, password):
		return _refuse(user, "a wrong password while turning it off", "wrong_password")
	if not _code_ok(user, get_otpsecret_for_(user), code):
		return _refuse(user, "a wrong code while turning it off", "wrong_code")
	_set_role(user, False)
	_forget_secret(user)
	clear_default(f"{user}_cc_2step_tries")
	_record(user, "Two-step sign-in turned off")
	_after_change(user, _("turned off"), keep_current=True)
	return {"state": "off"}


def reset_for(user: str) -> dict:
	"""A System Manager switches it off for someone who lost their phone; recorded with who did it. Not whitelisted:
	the People page (P3-21) calls it after its own checks."""
	frappe.only_for("System Manager")
	if not frappe.db.exists("User", user):
		raise frappe.DoesNotExistError(_("No such account"))
	frappe.db.get_value("User", user, "name", for_update=True)
	was_on = is_on(user)
	if was_on:
		_set_role(user, False)
	_forget_secret(user)
	clear_default(f"{user}_cc_2step_tries")
	_record(user, f"Two-step sign-in switched off by {frappe.session.user} (lost phone)")
	_after_change(user, _("switched off by a System Manager"), keep_current=False)
	return {"state": "off", "was_on": was_on}
