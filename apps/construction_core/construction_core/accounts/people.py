"""P3-21 (R-13; D-189, D-235): the People page, for System Managers only.

Every method checks `System Manager` in its own body (DR-5). Every write refuses Administrator, Guest, any System
Manager (the caller included) and any account holding a role outside OURS: the page manages the team's two roles, the
clients and their access, never the site's administrators. A role change stays within TEAM_ROLES, never makes a client
staff, and reads the roles back. A team invitation is an Access Invite of kind Staff through the same join page.
"""

import secrets

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, get_fullname, now_datetime, nowdate

from construction_core.accounts import two_step
from construction_core.onboarding import invites, mail
from construction_core.permissions import CLIENT_ROLE

TEAM_ROLES = ("Construction Manager", "Construction Staff")
OURS = {*TEAM_ROLES, CLIENT_ROLE, two_step.ROLE}
AUTOMATIC = {"All", "Guest", "Desk User"}
STAFF_DAYS = 7
MANY_ROWS = 50  # rows in one invite_staff_many call (T5)
STAFF_A_DAY = 200  # team invitations made on one day, one at a time or many (T5)


def _only():
	frappe.only_for("System Manager")


def _roles(person: str, lock: bool = False) -> set[str]:
	"""From the table, never the role cache; locked for a write, so a role another System Manager just gave is seen."""
	rows = frappe.db.sql(f"select role from `tabHas Role` where parent = %s and parenttype = 'User'"
		f"{' for update' if lock else ''}", person)
	return {r[0] for r in rows} - AUTOMATIC


def _read_back(person: str):
	"""After any save of the account: still nothing this page may not hold (D-189; a Role Profile job may add roles)."""
	roles = _roles(person, lock=True)
	if "System Manager" in roles or roles - OURS:
		frappe.throw(_("The account changed in a way this page does not manage. Nothing was saved."))


def _kind(person: str, roles: set[str]) -> str:
	if person in invites.RESERVED or "System Manager" in roles or roles - OURS:
		return "protected"  # shown, never changed here (D-189)
	if CLIENT_ROLE in roles:
		return "client"
	return "team" if roles & set(TEAM_ROLES) else "protected"  # an account with neither is set up in Desk


def _editable(person) -> str:
	"""The account a write may touch, or a refusal; the caller is checked first."""
	_only()
	stored = frappe.db.get_value("User", person, "name", for_update=True) if isinstance(person, str) else None
	if not stored:
		raise frappe.DoesNotExistError(_("No such account"))
	person = stored  # the stored name: "guest" or "GUEST " finds Guest in the database (P3-21 audit M1)
	if person in invites.RESERVED or _kind(person, _roles(person, lock=True)) == "protected":
		raise frappe.PermissionError(_("Administrator, System Managers and accounts with other system roles are managed "
			"in Desk, not here."))
	return person


def _record(person: str, text: str):
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "User", "reference_name": person,
		"content": f"{text}, by {frappe.session.user}"}).insert(ignore_permissions=True)


def _projects_of(person: str) -> list[str]:
	return frappe.get_all("Project Member", filters={"parenttype": "Construction Project", "user": person},
		pluck="parent", distinct=True)


@frappe.whitelist(methods=["GET"])
def people() -> dict:
	"""Every account but Guest, with what the page shows; the pending invitations; the two-step requirement."""
	_only()
	out = []
	for u in frappe.get_all("User", filters={"name": ("not in", ["Guest"])},
			fields=["name", "full_name", "email", "enabled", "user_type", "cc_job_title"], order_by="full_name asc"):
		roles = _roles(u.name)
		kind = _kind(u.name, roles)
		out.append({"person": u.name, "full_name": u.full_name or u.name, "email": u.email or u.name,
			"enabled": cint(u.enabled), "kind": kind, "role": next((r for r in TEAM_ROLES if r in roles), None),
			"two_step": two_step.is_on(u.name) or (two_step.required_for(u.name) and two_step._set_up(u.name)),
			"projects": _projects_of(u.name), "is_me": u.name == frappe.session.user, "job_title": u.cc_job_title})
	pending = []
	for inv in frappe.get_all("Access Invite", filters={"status": "Active", "kind": ("!=", "Owner")}, order_by="creation desc",
			fields=["name", "kind", "email", "full_name", "role", "project", "expires_on", "invited_by", "mail_state"]):
		row = frappe.get_doc("Access Invite", inv.name)
		if invites.effective_status(row) != "Active":
			continue
		pending.append({**inv, "invited_by_name": get_fullname(inv.invited_by) if inv.invited_by else None,
			"waiting": sum(1 for r in row.requests if r.status == "Waiting")})
	projects = frappe.get_all("Construction Project", fields=["name", "project_name"], order_by="project_name asc")
	return {"people": out, "invites": pending, "projects": projects, "roles": list(TEAM_ROLES),
		"two_step": two_step.requirement_status(), "mail_ready": mail.mail_ready()}


# --- team invitations -----------------------------------------------------------------------------------------------


def _staff_role(role) -> str:
	if role not in TEAM_ROLES:
		frappe.throw(_("Choose Construction Manager or Construction Staff."), frappe.PermissionError)
	return role


def _staff_share(inv, token, mail_token, mail_it) -> dict:
	link = invites.link_for(token)
	emailed = False
	if cint(mail_it):
		emailed = mail.send_staff_invite(inv, invites.link_for(mail_token))
		inv.db_set("mail_state", "Queued" if emailed else "Failed", update_modified=False)
	return {"invite": inv.name, "link": link, "qr": invites.qr_for(link), "expires_on": str(inv.expires_on),
		"emailed": emailed, "bound": True}


@frappe.whitelist(methods=["POST"])
def invite_staff(email=None, full_name=None, role=None, project=None, mail_it=1, job_title=None) -> dict:
	"""A team invitation to a new address (D-235): the person joins through the join page with that role."""
	_only()
	invites._require_mail()
	if frappe.db.count("Access Invite", {"kind": "Staff", "creation": (">=", get_datetime(nowdate()))}) >= STAFF_A_DAY:
		frappe.throw(_("{0} team invitations were made today, the most in one day. Send the rest tomorrow.").format(
			STAFF_A_DAY))
	email = invites._clean_email(email)
	if frappe.db.exists("User", email) or frappe.db.exists("User", {"email": email}):
		frappe.throw(_("{0} already has an account: change its role or projects here instead.").format(email))
	role = _staff_role(role)
	if project and (not isinstance(project, str) or not frappe.db.exists("Construction Project", project)):
		frappe.throw(_("No such project"))
	if frappe.db.exists("Access Invite", {"email": email, "kind": "Staff", "status": "Active"}):
		frappe.throw(_("{0} already has a team invitation: make a new link for it instead.").format(email))
	token, mail_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
	inv = frappe.get_doc({"doctype": "Access Invite", "kind": "Staff", "role": role, "email": email,
		"full_name": invites._plain(full_name), "job_title": invites._plain(job_title), "project": project or None,
		"status": "Active", "expires_on": add_days(now_datetime(), STAFF_DAYS), "token_hash": invites.token_hash(token),
		"mail_token_hash": invites.token_hash(mail_token), "invited_by": frappe.session.user, "mail_state": "Not sent"})
	inv.insert(ignore_permissions=True)  # System Manager-only doctype; the caller is one
	return _staff_share(inv, token, mail_token, mail_it)


@frappe.whitelist(methods=["POST"])
def invite_staff_many(rows=None) -> list:
	"""Several team invitations in one call (T5): each row is invite_staff's, in its own savepoint, so one bad row never
	stops the others. A result per row, in order: {email, ok, error}."""
	_only()
	invites._require_mail()
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	if not isinstance(rows, list) or not rows or len(rows) > MANY_ROWS:
		frappe.throw(_("Send 1 to {0} invitations at a time.").format(MANY_ROWS))
	out = []
	for row in rows:
		row = row if isinstance(row, dict) else {}
		email = row.get("email") if isinstance(row.get("email"), str) else None
		point, logged = "cc_staff_" + frappe.generate_hash(length=8), len(frappe.local.message_log)
		frappe.db.savepoint(point)
		try:
			invite_staff(email=email, **{k: row.get(k) for k in ("full_name", "role", "project", "job_title")})
		except (frappe.ValidationError, frappe.PermissionError) as e:
			frappe.db.rollback(save_point=point)
			del frappe.local.message_log[logged:]  # the row's own answer says it; no popup per row
			out.append({"email": email, "ok": False, "error": str(e) or _("This invitation could not be sent.")})
			continue
		frappe.db.release_savepoint(point)
		out.append({"email": email, "ok": True, "error": None})
	if any(r["ok"] for r in out):
		_mark_step("W9")
	return out


def _mark_step(step: str) -> None:
	"""The set-up wizard's step (accounts.setup, P3-52), where it is installed."""
	try:
		from construction_core.accounts import setup
	except ImportError:
		return
	if hasattr(setup, "mark"):
		setup.mark(step, "done")


def _staff_invite(invite):
	_only()
	if not isinstance(invite, str) or not frappe.db.exists("Access Invite", {"name": invite, "kind": "Staff"}):
		raise frappe.DoesNotExistError(_("No such team invitation"))
	return frappe.get_doc("Access Invite", invite, for_update=True)


@frappe.whitelist(methods=["POST"])
def renew_staff_invite(invite=None, mail_it=1) -> dict:
	inv = _staff_invite(invite)
	if inv.status in ("Used", "Revoked"):
		frappe.throw(_("This invitation can no longer be renewed."))
	if frappe.db.exists("User", inv.email) or frappe.db.exists("User", {"email": inv.email}):
		frappe.throw(_("{0} already has an account.").format(inv.email))
	today = frappe.utils.nowdate()
	count = cint(inv.renewals) if str(inv.renewed_on or "") == today else 0
	if count >= invites.RENEWALS_A_DAY:
		frappe.throw(_("This invitation was renewed too often today. Try again tomorrow."))
	token, mail_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
	inv.update({"token_hash": invites.token_hash(token), "mail_token_hash": invites.token_hash(mail_token),
		"status": "Active", "expires_on": add_days(now_datetime(), STAFF_DAYS), "codes_sent": 0, "mail_state": "Not sent",
		"renewals": count + 1, "renewed_on": today,
		"invited_by": frappe.session.user})  # the renewing System Manager sends it now (P3-21 review 3)
	invites._unprove(inv)
	inv.save(ignore_permissions=True)
	return _staff_share(inv, token, mail_token, mail_it)


@frappe.whitelist(methods=["POST"])
def revoke_staff_invite(invite=None) -> dict:
	inv = _staff_invite(invite)
	if inv.status == "Used":
		frappe.throw(_("This invitation was already used."))
	inv.update({"status": "Revoked", "revoked_by": frappe.session.user, "revoked_on": now_datetime()})
	invites._unprove(inv)
	inv.save(ignore_permissions=True)
	return {"invite": inv.name, "status": inv.status}


# --- one account ----------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def set_role(person=None, role=None) -> dict:
	"""Construction Manager or Construction Staff for a team account; never a client made staff (D-189)."""
	person = _editable(person)
	role = _staff_role(role)
	if CLIENT_ROLE in _roles(person):
		frappe.throw(_("A client account cannot be given a team role. Invite the person to the team instead."),
			frappe.PermissionError)
	doc = frappe.get_doc("User", person)
	doc.set("roles", [r for r in doc.roles if r.role not in TEAM_ROLES])
	doc.append("roles", {"role": role})
	doc.save(ignore_permissions=True)  # only one of TEAM_ROLES changes; the account was checked above
	after = _roles(person)
	if after & set(TEAM_ROLES) != {role} or after - OURS:
		frappe.throw(_("The role could not be changed."))  # read back after the save (D-189)
	_record(person, f"Role set to {role}")
	return {"person": person, "role": role}


@frappe.whitelist(methods=["POST"])
def set_job_title(person=None, job_title=None) -> dict:
	"""A team account's short job title (QD), seen by the team only; a client's is set per project (P3-04)."""
	person = _editable(person)
	if _kind(person, _roles(person)) != "team":
		frappe.throw(_("A client's job title is set on each project's Settings."), frappe.PermissionError)
	title = invites._plain(job_title)
	frappe.db.set_value("User", person, "cc_job_title", title)  # permlevel 1: never through the person's own save
	_record(person, f"Job title set to {title or 'none'}")
	return {"person": person, "job_title": title}


@frappe.whitelist(methods=["POST"])
def project_access(person=None, project=None, on=1) -> dict:
	"""Add a team account to a project's members, or take it off. A client joins only by invitation (D-198)."""
	person = _editable(person)
	if CLIENT_ROLE in _roles(person) and cint(on):
		frappe.throw(_("A client joins a project through an invitation."), frappe.PermissionError)
	if not isinstance(project, str) or not frappe.db.exists("Construction Project", project):
		raise frappe.DoesNotExistError(_("No such project"))
	doc = frappe.get_doc("Construction Project", project)
	has = any(r.user == person for r in doc.users)
	if cint(on) and not has:
		doc.append("users", {"user": person, "welcome_email_sent": 1})
	elif not cint(on) and has:
		doc.set("users", [r for r in doc.users if r.user != person])
	else:
		return {"person": person, "projects": _projects_of(person)}
	doc.save(ignore_permissions=True)  # the caller is a System Manager; the member guard still runs
	_record(person, f"{'Added to' if cint(on) else 'Removed from'} project {project}")
	return {"person": person, "projects": _projects_of(person)}


@frappe.whitelist(methods=["POST"])
def set_access(person=None, on=0) -> dict:
	"""Turn an account off (its sessions end at once, P3-13; its invitations stop) or back on."""
	person = _editable(person)
	doc = frappe.get_doc("User", person)
	doc.enabled = 1 if cint(on) else 0
	doc.save(ignore_permissions=True)  # P3-13's on_user_update ends the sessions and stamps the account
	_read_back(person)
	if not cint(on):
		for name in frappe.get_all("Access Invite", filters={"status": "Active"}, or_filters={"invited_by": person,
				"email": doc.email or person}, pluck="name"):
			inv = frappe.get_doc("Access Invite", name, for_update=True)
			inv.update({"status": "Revoked", "revoked_by": frappe.session.user, "revoked_on": now_datetime()})
			invites._unprove(inv)
			inv.save(ignore_permissions=True)
	_record(person, "Access turned on" if cint(on) else "Access turned off")
	return {"person": person, "enabled": doc.enabled}


@frappe.whitelist(methods=["POST"])
def send_reset(person=None) -> dict:
	"""Frappe's own reset email (a hashed, single-use key); we never see or set a password."""
	person = _editable(person)
	if not cint(frappe.db.get_value("User", person, "enabled")):
		frappe.throw(_("Turn the account's access on first."))
	if not mail.mail_ready():
		frappe.throw(_("Set up outgoing email first."))
	frappe.get_doc("User", person)._reset_password(send_email=True)  # Frappe's own key and mail
	_record(person, "Password reset email sent")
	return {"person": person, "sent": True}


@frappe.whitelist(methods=["POST"])
def two_step_off(person=None) -> dict:
	"""A lost phone: two-step sign-in is switched off (two_step.reset_for records it)."""
	person = _editable(person)
	out = two_step.reset_for(person)
	_read_back(person)
	return out
