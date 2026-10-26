"""P3-17, P3-18 (R-13; D-187, D-188, D-197, D-213, D-214, D-216, D-219, D-220): the sign-in-free join page's calls.

A person opens `/join#k=<token>`; the page keeps the token out of the address bar and posts it here. A token is one of:

- `bound`: the link the team copied or showed for an invitation with an address; a code mailed there proves it;
- `mailed`: the link only ever mailed to that address (D-219); opening it proves the inbox, so no code is asked;
- `open`: a link with no address; each person types theirs, proves it with a code and waits for a manager (D-188);
- `approved`: a person's own link once a manager approved them (D-220): 48 hours, single use, mailed to them only.

Each person proving an address has an Access Request row holding their code and their check, so people on one open
link never disturb each other. A right code gives the page a `proof` secret (only its sha256 is kept); every later
step needs it, so knowing someone's request is not enough to act as them.

A team invitation (kind Staff, P3-21, D-235) uses the bound and mailed links only: the person gives a name and a
password under the site's policy, and finish makes a team account with the invitation's role, after checking that its
inviter is still an enabled System Manager. The owner's invitation (kind Owner, P3-54, D-346, T1) takes the same steps;
its finish grants exactly OWNER_ROLES, after checking that its inviter is Administrator and set-up is still unfinished.

Each method is a guest POST that refuses a signed-in session and a request another site made, checks the link every
time (by timestamp, never the scheduler) and answers a state: it never raises for a person's mistake, so nothing typed
reaches a traceback or the Error Log. It never signs anyone in (no `login_as`); the person signs in normally.
"""

import functools
import hashlib
import hmac
import re
import secrets
import time
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from construction_core.accounts import setup
from construction_core.onboarding import invites, mail
from construction_core.onboarding.privacy import VERSION as CONSENT_VERSION  # D-213: the notice's one version (P3-83)
from construction_core.permissions import CLIENT_ROLE

CODE_MINUTES, CODE_TRIES, CODE_GAP_SECONDS, VERIFIED_MINUTES = 15, 5, 60, 30
CODES_PER_REQUEST, CODES_BOUND, CODES_OPEN = 6, 6, 20  # a person's codes; all codes of a bound or an open link
OPEN_PEOPLE = 5  # proven people on one open link (D-220)
MIN_PASSWORD, MAX_PASSWORD, CLIENT_SCORE = 8, 256, 1  # D-219: simple for clients; the commonest and their own name refused
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
PLAIN_EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$")  # D-222: nothing a staff screen could misread
MOBILE = re.compile(r"^\+?[0-9][0-9 ()-]{5,22}$")
STAFF_ROLES = ("Construction Manager", "Construction Staff")  # what a team invitation may give (D-189, D-235)
OWNER_ROLES = ("System Manager", "Construction Manager")  # what the owner's invitation gives, never its role field (D-346)
TEAM_KINDS = ("Staff", "Owner")
LIMITS = {"ip_per_hour": 300, "address_per_day": 10}  # generous ceilings; the per-link caps carry the load
INVALID = {"state": "invalid"}
SEND_FLOOR_SECONDS = 0.35  # every send_code answer takes at least this long, mail or none (P3-23, D-241)


def _limits() -> dict:
	return {**LIMITS, **(frappe.conf.get("cc_join_limits") or {})}


def _count(key: str, seconds: int) -> int:
	k = frappe.cache.make_key(f"cc:join:{key}")
	n = frappe.cache.incrby(k, 1)
	if n == 1 or frappe.cache.ttl(k) < 0:
		frappe.cache.expire(k, seconds)
	return n


def guest_call(fn):
	"""The shared preamble and the never-a-5xx answer of every join method."""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		if frappe.session.user != "Guest":
			return {"state": "signed_in"}
		request = getattr(frappe.local, "request", None)
		if request:
			origin = request.headers.get("Origin")
			if origin and urlparse(origin).netloc.lower() != (request.host or "").lower():
				return INVALID
			if request.headers.get("Sec-Fetch-Site") == "cross-site":
				return INVALID
			if _count(f"ip:{frappe.local.request_ip}", 3600) > cint(_limits()["ip_per_hour"]):
				return {"state": "try_later"}
		try:
			return fn(*args, **kwargs)
		except Exception as e:
			frappe.db.rollback()
			if "Throttled" in str(e) or isinstance(e, (frappe.QueryDeadlockError, frappe.QueryTimeoutError)):
				return {"state": "try_later"}  # passing: the link still stands (P3-17 audit S1)
			frappe.log_error(title=f"construction_core: join {fn.__name__} failed",
				message=f"{type(e).__name__} (details withheld: the request carries a code or a password)",
				defer_insert=True)
			return INVALID

	return wrapper


# --- what a token is ------------------------------------------------------------------------------------------------


def _resolve(token, lock=False):
	"""(invitation, kind, request or None) for a token that stands, or None. A link the team holds, or one mailed to the
	invitation's address, stands while the invitation is active; an approved person's link stands for 48 hours after
	the approval, even once the open link itself has run out."""
	if not isinstance(token, str) or not TOKEN.match(token):
		return None
	h = invites.token_hash(token)
	name, kind, row_name = frappe.db.get_value("Access Invite", {"token_hash": h}, "name"), "staff", None
	if not name:
		name, kind = frappe.db.get_value("Access Invite", {"mail_token_hash": h}, "name"), "mailed"
	if not name:
		found = frappe.db.get_value("Access Request", {"finish_token_hash": h, "parenttype": "Access Invite"},
			["name", "parent"], as_dict=True)
		if found:
			name, kind, row_name = found.parent, "approved", found.name
	if not name:
		return None
	# Locked: the invitation and its requests are read with FOR UPDATE, so they are the latest committed, whatever the
	# database's snapshot (D-222); every writer of them takes the same lock first.
	inv = frappe.get_doc("Access Invite", name, for_update=bool(lock))
	if inv.kind not in ("Client", *TEAM_KINDS) or inv.status in ("Revoked", "Used"):
		return None
	if inv.kind in TEAM_KINDS and (kind == "approved" or not inv.email
			or (inv.kind == "Staff" and inv.role not in STAFF_ROLES)):
		return None  # a team or owner invitation is always bound to its address; a team one has a listed role (D-235)
	if kind == "approved":
		row = _row(inv, row_name)
		if not row or row.status != "Approved" or row.finish_token_hash != h or not row.finish_expires_on \
				or get_datetime(row.finish_expires_on) <= now_datetime():
			return None
		return inv, kind, row
	if (inv.token_hash if kind == "staff" else inv.mail_token_hash) != h:
		return None  # a renew between the lookup and the lock: the old link is dead (P3-18 audit S1)
	if invites.effective_status(inv) != "Active" or (kind == "mailed" and not inv.email) or not _inviter_may(inv):
		return None
	if kind == "staff":
		kind = "bound" if inv.email else "open"
	return inv, kind, None


def _inviter_may(inv) -> bool:
	"""The one who sent the link is still enabled and may still invite clients to the project (D-214, D-222); a team
	invitation's sender is still an enabled System Manager (D-235); the owner's is Administrator's, before set-up is
	finished (D-346, T1)."""
	if inv.kind == "Owner":
		return inv.invited_by == "Administrator" and not setup.finished()
	if inv.kind == "Staff":
		return bool(inv.invited_by and cint(frappe.db.get_value("User", inv.invited_by, "enabled"))
			and frappe.db.exists("Has Role", {"parent": inv.invited_by, "parenttype": "User",
				"role": "System Manager"}))  # the table, never the role cache (P3-21 review 5)
	return _may(inv.invited_by, inv.project)


def _may(user, project) -> bool:
	if not user or not cint(frappe.db.get_value("User", user, "enabled")):
		return False
	doc = frappe.get_doc("Construction Project", project)
	return bool(frappe.has_permission("Construction Project", "manage_clients", doc=doc, user=user))


def _counted(inv, but=None) -> int:
	"""Proven people on an open link who are not declined (D-220, D-222)."""
	return sum(1 for r in inv.requests if r.verified_on and r.status != "Declined" and r.name != but)


def _row(inv, request_id):
	return next((r for r in inv.requests if isinstance(request_id, str) and r.name == request_id), None)


def _row_for(inv, email):
	return next((r for r in inv.requests if (r.email or "").lower() == (email or "").lower()), None)


def _proven(inv, proof):
	"""The request whose address the `proof` from check_code proves, while its 30 minutes last; or None."""
	if not isinstance(proof, str) or not TOKEN.match(proof):
		return None
	h = invites.token_hash(proof)
	row = next((r for r in inv.requests if r.proof_hash and hmac.compare_digest(r.proof_hash, h)), None)
	if row and row.status == "Pending" and row.verified_until and get_datetime(row.verified_until) > now_datetime():
		return row
	return None


def _mask(email: str) -> str:
	local, _sep, domain = (email or "").partition("@")
	host, _dot, tld = domain.rpartition(".")
	return f"{local[:1]}•••@{host[:1]}•••.{tld}" if host else f"{local[:1]}•••@{domain}"


def _hmac(inv, row, email: str, code: str) -> str:
	from frappe.utils.password import get_encryption_key

	message = f"{inv.name}|{row.name}|{email}|{code}".encode()
	return hmac.new(get_encryption_key().encode(), message, hashlib.sha256).hexdigest()


def _account(email: str):
	return frappe.db.get_value("User", {"name": email}, ["name", "user_type", "enabled"], as_dict=True) or \
		frappe.db.get_value("User", {"email": email}, ["name", "user_type", "enabled"], as_dict=True)


def _usable(email: str) -> bool:
	"""A new address, or an enabled client account: never the team, Administrator or a turned-off account."""
	account = _account(email)
	return not account or (account.name not in invites.RESERVED and account.user_type == "Website User"
		and cint(account.enabled))


def _code_live(row) -> bool:
	return bool(row and row.status == "Pending" and row.code_hmac and row.code_expires_on
		and get_datetime(row.code_expires_on) > now_datetime())


# --- the calls ------------------------------------------------------------------------------------------------------
# Arguments are untyped: Frappe's type check would answer 417 before guest_call (P3-17 review F1); each is checked here.


@frappe.whitelist(allow_guest=True, methods=["POST"], xss_safe=True)
@guest_call
def look(token=None, request_id=None, proof=None) -> dict:
	"""What the page may show, and where the person left off. Writes nothing. Before an address is proven it names
	nobody (P3-17 review F3): only the company, the inviter's first name and, on a bound link, the masked address."""
	found = _resolve(token)
	if not found:
		return INVALID
	inv, kind, row = found
	out = {"state": "ready", "kind": kind, "company": mail.brand(), "inviter": mail.first_name(inv.invited_by),
		"masked": _mask(inv.email) if inv.email else "", "stage": "welcome", "name": "", "existing": False,
		"team": inv.kind in TEAM_KINDS}
	if kind == "approved":  # their own link, mailed to their proven address
		out.update({"masked": _mask(row.email), "stage": "finish", "name": row.full_name or "",
			"existing": bool(_account(row.email))})
	elif kind == "mailed":  # opening the mail proved the inbox (D-219)
		out.update({"stage": "details", "name": inv.full_name or "", "existing": bool(_account(inv.email))})
	elif _proven(inv, proof):
		proven = _proven(inv, proof)
		out.update({"stage": "details", "masked": _mask(proven.email),
			"name": (inv.full_name if kind == "bound" else "") or "", "existing": bool(_account(proven.email))})
	else:
		pending = _row(inv, request_id) or (_row_for(inv, inv.email) if kind == "bound" else None)
		if pending and pending.status == "Waiting" and kind == "open":
			out.update({"stage": "waiting", "masked": _mask(pending.email)})
		elif _code_live(pending):
			out.update({"stage": "code", "masked": _mask(pending.email), "request": pending.name})
	return out


@frappe.whitelist(allow_guest=True, methods=["POST"], xss_safe=True)
@guest_call
def send_code(token=None, email=None) -> dict:
	"""Mail a code to the address being proven: the invitation's own, or the one typed on an open link. Only when
	asked: a link scanner that runs the page sends none. Every address gets the same answer, used or not, in the same
	time: a team address gets no mail, so the answer waits as long as a mailed one would (P3-23, D-241). Frappe sends
	a mail after the commit, so the wait runs after the commit too, registered last: after the mail, and after the
	invitation's row lock is released."""
	started = time.monotonic()
	out = _send_code(token, email)
	frappe.db.after_commit.add(lambda: time.sleep(max(0.0, SEND_FLOOR_SECONDS - (time.monotonic() - started))))
	return out


def _send_code(token, email) -> dict:
	found = _resolve(token, lock=True)
	if not found:
		return INVALID
	inv, kind, _ignored = found
	if kind not in ("bound", "open"):
		return {"state": "not_needed"}
	if kind == "bound":
		address = inv.email
	else:
		address = (email if isinstance(email, str) else "").strip().lower()
		if not address or len(address) > 140 or not PLAIN_EMAIL.match(address) \
				or frappe.utils.validate_email_address(address, throw=False) != address:
			return {"state": "email_invalid"}
	row = _row_for(inv, address)
	if row and row.status != "Pending":  # already further: the same answer as a new address, and no mail (D-222)
		return {"state": "sent", "masked": _mask(address)}
	if cint(inv.codes_sent) >= (CODES_BOUND if kind == "bound" else CODES_OPEN):
		return {"state": "too_many_codes"}
	if not row and kind == "open" and _counted(inv) >= OPEN_PEOPLE:
		return {"state": "full"}
	if row and cint(row.codes_sent) >= CODES_PER_REQUEST:
		return {"state": "too_many_codes"}
	if row and row.code_expires_on:
		sent_at = add_to_date(get_datetime(row.code_expires_on), minutes=-CODE_MINUTES)
		wait = CODE_GAP_SECONDS - int((now_datetime() - sent_at).total_seconds())
		if wait > 0:  # the person who asked keeps their request in the page; nobody else learns it (D-222)
			return {"state": "wait", "seconds": wait, "masked": _mask(address)}
	if _count(f"address:{address}", 86400) > cint(_limits()["address_per_day"]):
		return {"state": "try_later"}
	if not row:
		inv.append("requests", {"email": address, "status": "Pending"})
		inv.save(ignore_permissions=True)  # a guest adds a person to an invitation only here, before any proof
		row = _row_for(inv, address)
	code = f"{secrets.randbelow(10**6):06d}"
	row.db_set({"code_hmac": _hmac(inv, row, address, code), "code_tries": 0, "codes_sent": cint(row.codes_sent) + 1,
		"code_expires_on": add_to_date(now_datetime(), minutes=CODE_MINUTES)}, update_modified=False)
	frappe.db.sql("update `tabAccess Invite` set codes_sent = codes_sent + 1 where name = %s", inv.name)
	# The mail is a job for every address, so the request does the same work whoever asked (P3-23, D-241); the job
	# sends nothing to an address that is the team's or turned off. Tests run it at once.
	frappe.enqueue("construction_core.onboarding.join.mail_code", queue="short", enqueue_after_commit=True,
		now=frappe.in_test, invite=inv.name, address=address, code=code, request=row.name)
	return {"state": "sent", "masked": _mask(address), "request": row.name}


def mail_code(invite: str, address: str, code: str, request: str):
	"""The job behind send_code (not whitelisted): the code goes only to a usable address."""
	if _usable(address) and frappe.db.exists("Access Invite", invite):
		mail.send_code(frappe.get_doc("Access Invite", invite), address, code, request=request)


@frappe.whitelist(allow_guest=True, methods=["POST"], xss_safe=True)
@guest_call
def check_code(token=None, request_id=None, code=None) -> dict:
	"""Check a person's code. A wrong one counts against it and is answered, never raised, so its count is kept. A right
	one answers the `proof` the later steps need, once."""
	found = _resolve(token, lock=True)
	if not found:
		return INVALID
	inv, kind, _ignored = found
	row = _row(inv, request_id)
	if kind not in ("bound", "open") or not row or row.status != "Pending":
		return INVALID
	if not _code_live(row):
		return {"state": "code_expired"}
	if cint(row.code_tries) >= CODE_TRIES:
		return {"state": "locked"}
	if kind == "open" and not row.verified_on and _counted(inv, but=row.name) >= OPEN_PEOPLE:
		return {"state": "full"}  # people who asked at once are counted again here (D-222)
	digits = re.sub(r"\D", "", code if isinstance(code, str) else "")[:6]
	if not hmac.compare_digest(_hmac(inv, row, row.email, digits), row.code_hmac):
		frappe.db.sql("update `tabAccess Request` set code_tries = code_tries + 1 where name = %s", row.name)
		tries = cint(row.code_tries) + 1
		if tries >= CODE_TRIES:
			row.db_set({"code_hmac": None}, update_modified=False)
			return {"state": "locked"}
		return {"state": "wrong", "left": CODE_TRIES - tries}
	proof = secrets.token_urlsafe(32)
	row.db_set({"code_hmac": None, "proof_hash": invites.token_hash(proof), "verified_on": row.verified_on or now_datetime(),
		"verified_until": add_to_date(now_datetime(), minutes=VERIFIED_MINUTES)}, update_modified=False)
	return {"state": "verified", "proof": proof, "existing": bool(_account(row.email)),
		"name": (inv.full_name if kind == "bound" else "") or ""}


def _clean(value, limit) -> str | None:
	return invites._plain(value if isinstance(value, str) else None, limit)


def _weak(password: str, inputs) -> dict | None:
	"""D-219: 8 characters or more; refused only when it is among the commonest or is the person's own name, address or
	company (zxcvbn, with those as its inputs, scores it 0)."""
	from frappe.utils.password_strength import test_password_strength

	if len(password) < MIN_PASSWORD:
		return {"state": "weak", "warning": _("Use at least {0} characters.").format(MIN_PASSWORD)}
	if len(password) > MAX_PASSWORD:
		return {"state": "weak", "warning": _("Use at most {0} characters.").format(MAX_PASSWORD)}
	words = []
	for value in inputs:  # the name, the address and the company, whole and in parts, so none of them is the password
		if value:
			value = str(value).lower()
			words += [value, value.replace(" ", ""), value.split("@")[0], *re.split(r"[\s.@_-]+", value)]
	result = test_password_strength(password, user_inputs=[w for w in dict.fromkeys(words) if len(w) > 2])
	if cint(result.get("score")) < CLIENT_SCORE:
		return {"state": "weak", "warning": _("That password is too easy to guess. Add another word or a few numbers.")}
	return None


def _profile(account: str, row, inv):
	"""The client record (D-212): a profile the team already keeps wins; a join fills only what is empty."""
	existing = frappe.db.get_value("Client Profile", {"account": account})
	profile = frappe.get_doc("Client Profile", existing) if existing else \
		frappe.get_doc({"doctype": "Client Profile", "account": account, "full_name": row.full_name})
	if row.full_name and not profile.full_name:
		profile.full_name = row.full_name
	if row.mobile_no and not profile.mobile_no:
		profile.mobile_no = row.mobile_no
	if row.company_name and not profile.company_name:
		profile.company_name = row.company_name
	profile.update({"consent_version": row.consent_version or CONSENT_VERSION, "consent_on": row.consent_on or now_datetime(),
		"joined_from": profile.joined_from or inv.name})
	profile.save(ignore_permissions=True)


def add_member(inv, project, account: str, row):
	"""The account joins the project as a client contact, with its Client Profile, and the managers are told. Callers
	check every right first: finish (the link, the proof, the inviter) and invites.decide (manage_clients)."""
	user = frappe.get_doc("User", account)
	if CLIENT_ROLE not in {r.role for r in user.roles}:
		user.append("roles", {"role": CLIENT_ROLE})  # as add_client does for a plain Website User
		user.save(ignore_permissions=True)
	if account not in {r.user for r in project.users}:
		project.append("users", {"user": account, "welcome_email_sent": 1, "cc_workspace_role": "Client",
			"job_title": inv.job_title})
		project.flags.cc_join_users = {account}
		project.save(ignore_permissions=True)  # the member guard lets this one row in (D-206)
	_profile(account, row, inv)
	from construction_core import notifications

	notifications.notify(invites._managers(project), notifications.CLIENT_JOINED, project, actor=account)


def _finish_staff(inv, row, email, full_name, new_password) -> dict:
	"""A team invitation (D-235): a new team account with the invitation's role, never over an existing account. The
	owner's (D-346): the account gets OWNER_ROLES, and W4 is done."""
	owner = inv.kind == "Owner"
	if _account(email) or not (owner or inv.role in STAFF_ROLES) or not _inviter_may(inv):
		return INVALID
	name = _clean(full_name, 140) or inv.full_name
	if not name:
		return {"state": "name_needed"}
	password = new_password if isinstance(new_password, str) else ""
	weak = _weak_staff(password, (name, email))
	if weak:
		return weak
	user = frappe.get_doc({"doctype": "User", "email": email, "first_name": name, "send_welcome_email": 0,
		"user_type": "System User", "cc_job_title": inv.get("job_title") or "", "roles": [{"role": r} for r in (OWNER_ROLES if owner else (inv.role,))]})
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)  # a guest makes a team account only here, for its proven address (D-235)
	from frappe.utils.password import update_password

	update_password(user.name, password)  # after the insert: the password never sits in a queued job
	if not row:
		inv.append("requests", {"email": email, "status": "Pending", "verified_on": now_datetime()})
		row = _row_for(inv, email)
	row.update({"status": "Joined", "account": user.name, "full_name": name, "verified_until": None, "proof_hash": None,
		"verified_on": row.verified_on or now_datetime()})
	inv.update({"status": "Used", "used_on": now_datetime(), "account": user.name})
	inv.save(ignore_permissions=True)
	if owner:
		setup.mark("W4", "done", by=user.name)  # the session is Guest: the step names the owner who joined
	if inv.project and frappe.db.exists("Construction Project", inv.project):
		project = frappe.get_doc("Construction Project", inv.project)
		if user.name not in {r.user for r in project.users}:
			project.append("users", {"user": user.name, "welcome_email_sent": 1})
			project.save(ignore_permissions=True)
	return {"state": "done", "existing": False, "login": "/login?redirect-to=" + frappe.utils.quoted("/workspace")}


def _weak_staff(password: str, inputs) -> dict | None:
	"""A team password keeps the site's policy (D-219): the site's minimum score, at least 2."""
	from frappe.utils.password_strength import test_password_strength

	if len(password) < 10 or len(password) > MAX_PASSWORD:
		return {"state": "weak", "warning": _("Use 10 to {0} characters.").format(MAX_PASSWORD)}
	words = [w for v in inputs if v for w in re.split(r"[\s.@_-]+", str(v).lower()) if len(w) > 2]
	result = test_password_strength(password, user_inputs=words)
	needed = max(cint(frappe.db.get_single_value("System Settings", "minimum_password_score")), 2)
	if cint(result.get("score")) < needed:
		return {"state": "weak", "warning": _("That password is too easy to guess. Use a longer one, such as a short "
			"sentence.")}
	return None


def _new_account(email, name, password) -> str:
	user = frappe.get_doc({"doctype": "User", "email": email, "first_name": name, "send_welcome_email": 0,
		"user_type": "Website User", "roles": [{"role": CLIENT_ROLE}]})
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)  # a guest makes an account only here, for its proven address (D-188)
	from frappe.utils.password import update_password

	update_password(user.name, password)  # after the insert: the password never sits in a queued job
	return user.name


@frappe.whitelist(allow_guest=True, methods=["POST"], xss_safe=True)
@guest_call
def finish(token=None, proof=None, full_name=None, mobile_no=None, company_name=None, new_password=None,
		consent=0) -> dict:
	"""Once, under the invitation's row lock: on a bound, mailed or approved link, make the account (or use the client's
	own) and the membership; on an open link, send the person's details to the team, who approve or decline them."""
	found = _resolve(token, lock=True)
	if not found:
		return INVALID
	inv, kind, row = found
	if kind == "mailed":
		row = _row_for(inv, inv.email)
		if row and row.status != "Pending":
			return INVALID
	elif kind in ("bound", "open"):
		row = _proven(inv, proof)
		if not row:
			return {"state": "verify_again"}
	email = row.email if row else inv.email
	if not _usable(email):
		return INVALID
	if inv.kind in TEAM_KINDS:
		return _finish_staff(inv, row, email, full_name, new_password)
	project = frappe.get_doc("Construction Project", inv.project)
	if not _may(row.decided_by if kind == "approved" else inv.invited_by, inv.project):
		return INVALID  # whoever sent or approved the link left or lost the right: it no longer stands (D-214)
	if kind == "approved":
		pass  # the details and the consent were given before the approval
	else:
		if not cint(consent):
			return {"state": "consent_needed"}
		name = _clean(full_name, 140) or (inv.full_name if kind != "open" else None)
		if not name:
			return {"state": "name_needed"}
		mobile = (mobile_no if isinstance(mobile_no, str) else "").strip()
		if mobile and not MOBILE.match(mobile):
			return {"state": "mobile_invalid"}
		if kind == "open" and not mobile:
			return {"state": "mobile_needed"}  # so the team can call before approving (R-13)
		if not row:  # the mailed link: the address was proven by opening it
			inv.append("requests", {"email": email, "status": "Pending", "verified_on": now_datetime()})
			row = _row_for(inv, email)
		row.update({"full_name": name, "mobile_no": mobile or None, "company_name": _clean(company_name, 140),
			"consent_version": CONSENT_VERSION, "consent_on": now_datetime()})
	if kind == "open":  # a person on an open link waits for the team (D-188)
		row.update({"status": "Waiting", "verified_until": None, "proof_hash": None})
		inv.save(ignore_permissions=True)
		from construction_core import notifications

		notifications.notify(invites._managers(project), notifications.CLIENT_WAITING, project, actor="Guest")
		return {"state": "waiting"}
	account = _account(email)
	if account:
		account_name = account.name  # an existing client keeps their password and names
	else:
		password = new_password if isinstance(new_password, str) else ""
		weak = _weak(password, (row.full_name, email, row.company_name))
		if weak:
			return weak
		account_name = _new_account(email, row.full_name, password)
	row.update({"status": "Joined", "account": account_name, "verified_until": None, "proof_hash": None,
		"finish_token_hash": None, "verified_on": row.verified_on or now_datetime()})
	if kind != "approved":  # a bound invitation serves one person; an open link stays open for the others
		inv.update({"status": "Used", "used_on": now_datetime(), "account": account_name})
	inv.save(ignore_permissions=True)
	add_member(inv, project, account_name, row)
	return {"state": "done", "existing": bool(account),
		"login": "/portal/login?redirect-to=" + frappe.utils.quoted(f"/portal/{project.name}")}
