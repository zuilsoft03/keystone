"""Client onboarding (§5.2 step 2, D-068): a project manager adds a client user to a project.

Frappe lets only a System Manager create users, so this method creates exactly one kind: a Website User whose only
role is ``Construction Client`` (no Desk access, §2.5). It needs the ``manage_clients`` Permission Type on the
Project (§2.4) and never touches a staff (System User) account.

Since P3-19 (D-198) this is an internal helper, never a whitelisted method: the team invites clients through
`onboarding.invites`, and a client joins through the join page. Seed, staging, fixtures and tests still call it.

A contact's job title (P3-04, D-151) is a permlevel-1 field of their member row: the project team sees it, a client
never receives it, and it changes only through the project's own save (D-119).
"""

import frappe
from frappe import _
from frappe.utils import validate_email_address

from construction_core.permissions import CLIENT_ROLE

RESERVED = {"Administrator", "Guest"}


def add_client(project: str, email: str, full_name: str | None = None, job_title: str | None = None) -> str:
	doc = frappe.get_doc("Construction Project", project)
	frappe.has_permission("Construction Project", "manage_clients", doc=doc, throw=True)
	email = (email or "").strip().lower()
	if not email or any(c in email for c in ",;\n\r\t ") or validate_email_address(email, throw=True) != email:
		frappe.throw(_("Give exactly one email address"))
	# User.email is not unique: match on both name and email, and refuse anything but one plain Website User.
	matches = frappe.get_all("User", or_filters={"name": email, "email": email}, fields=["name", "user_type"])
	if len(matches) > 1 or any(m.name in RESERVED or m.user_type != "Website User" for m in matches):
		frappe.throw(_("{0} is a staff or reserved account: add staff as project members instead").format(email),
			frappe.PermissionError)
	user = matches[0] if matches else None
	if user:
		u = frappe.get_doc("User", user.name)
		if CLIENT_ROLE not in {r.role for r in u.roles}:
			u.append("roles", {"role": CLIENT_ROLE})
			# ignore_permissions: only the client role is added, to a Website User (checked above).
			u.save(ignore_permissions=True)
	else:
		u = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": (full_name or email.split("@")[0]).strip(),
			"user_type": "Website User", "roles": [{"role": CLIENT_ROLE}],
			# The welcome mail carries the set-password link; without an outgoing account Frappe would throw.
			"send_welcome_email": int(bool(frappe.db.exists("Email Account", {"enable_outgoing": 1}))),
		})
		# ignore_permissions: the only account this creates is a Website User with the client role.
		u.insert(ignore_permissions=True)
	title = (job_title or "").strip()[:140] or None
	row = next((r for r in doc.users if r.user == u.name), None)
	if not row:
		# welcome_email_sent=1: ERPNext's project mail is not used (Frappe's welcome mail is), and it throws on a
		# site with no Email Account (ARCHITECTURE §2.3).
		doc.append("users", {"user": u.name, "welcome_email_sent": 1, "cc_workspace_role": "Client", "job_title": title})
		doc.flags.cc_join_users = {u.name}  # the one sanctioned way a client joins (D-198, D-206)
		doc.save()
	elif title and row.cc_workspace_role == "Client" and row.job_title != title:
		row.job_title = title  # inviting a contact again with a title updates it
		doc.save()
	return u.name
