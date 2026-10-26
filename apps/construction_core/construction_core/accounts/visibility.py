"""P3-15 (R-13; D-194, D-198, D-200, D-206): who sees whom, and who may make someone a client of a project.

- Contact and Address are for System Managers only (`restrict_contacts`): before this, the role All could create a
  Contact for a future person, which Frappe's create_contact later filled with that person's name and mobile.
- Staff see themselves, the team and the clients of their own projects in account lists and searches
  (`user_query_conditions`, `user_has_permission`); before this, any staff member listed every account.
- No account holds the client role with a desk role (`refuse_mixed_roles`), and a Client-tagged project row never
  belongs to a staff account.
- A client joins a project only through the invitation path (`guard_members`): a project save by anyone but a System
  Manager or Administrator refuses a new client row unless the project document names that user in
  `doc.flags.cc_join_users`, which only `clients.add_client` (and later the join flow) sets.
- A client with no project cannot sign in (`refuse_client_without_project`).
"""

import frappe
from frappe import _

from construction_core.permissions import CLIENT_ROLE, allowed_projects, is_client

CONTACT_DOCTYPES = ("Contact", "Address")
MANAGER_ROLES = frozenset({"System Manager"})


def _is_manager(user: str) -> bool:
	return user == "Administrator" or bool(MANAGER_ROLES & set(frappe.get_roles(user)))


# --- Contact and Address --------------------------------------------------------------------------------------------


def restrict_contacts():
	"""Custom DocPerm rows replace a doctype's standard permissions: keep System Manager's, drop every other role's."""
	from frappe.permissions import setup_custom_perms

	for doctype in CONTACT_DOCTYPES:
		setup_custom_perms(doctype)  # copies the standard rows once; a no-op when custom rows exist
		frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": ("!=", "System Manager")})
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "System Manager", "permlevel": 0}):
			frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType",
				"parentfield": "permissions", "role": "System Manager", "permlevel": 0, "read": 1, "write": 1,
				"create": 1, "delete": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1}).insert(
				ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)


# --- the account list ---------------------------------------------------------------------------------------------


def _clients_of(user: str) -> set[str]:
	projects = allowed_projects(user)
	if not projects:
		return set()
	return set(frappe.get_all("Project Member", filters={"parenttype": "Construction Project", "parent": ("in", projects)},
		pluck="user"))


def user_query_conditions(user=None, doctype=None):
	"""permission_query_conditions for User (ANDed with Frappe's own, so it also narrows Frappe's user_query)."""
	user = user or frappe.session.user
	if _is_manager(user):
		return ""
	projects = allowed_projects(user)
	clients = ("`tabUser`.name in (select pm.user from `tabProject Member` pm where pm.parenttype = "
		"'Construction Project' and pm.parent in ({}))".format(", ".join(frappe.db.escape(p) for p in projects))
		if projects else "0")
	return f"(`tabUser`.name = {frappe.db.escape(user)} or `tabUser`.user_type = 'System User' or {clients})"


def user_has_permission(doc, ptype=None, user=None):
	"""has_permission for User: a client account is visible only to its own projects' people (D-194). True means no
	objection: in v16 a hook that returns None refuses (frappe.permissions.has_controller_permissions; P3-15 audit M1)."""
	user = user or frappe.session.user
	if _is_manager(user) or doc.name == user or doc.get("user_type") != "Website User":
		return True
	return doc.name in _clients_of(user)


# --- roles and rows ---------------------------------------------------------------------------------------------


def refuse_mixed_roles(doc, method=None):
	"""User validate: the client role never sits beside a role with desk access, which would make the account staff
	everywhere (Frappe sets user_type from desk_access) while its project rows still say Client."""
	if doc.name == "Administrator":
		return
	roles = {r.role for r in doc.get("roles") or []}
	if CLIENT_ROLE not in roles:
		return
	desk = frappe.get_all("Role", filters={"name": ("in", list(roles - {CLIENT_ROLE})), "desk_access": 1}, pluck="name")
	if desk:
		frappe.throw(_("A client account cannot also hold a team role ({0}).").format(", ".join(sorted(desk))),
			frappe.PermissionError)


def guard_members(doc, method=None):
	"""Construction Project validate: client rows join only through the invitation path (D-198, D-206)."""
	before = doc.get_doc_before_save()
	old = {r.user for r in (before.get("users") if before else [])}
	allowed = set(doc.flags.cc_join_users or ())
	manager = _is_manager(frappe.session.user)
	for row in doc.get("users") or []:
		if not row.user:
			continue
		client = is_client(row.user)
		if client and row.cc_workspace_role != "Client":
			row.cc_workspace_role = "Client"  # an account made a client later is listed as one (P3-15 audit S1)
		if row.cc_workspace_role == "Client" and not client:
			frappe.throw(_("{0} is a team account and cannot be a client contact.").format(row.user),
				frappe.PermissionError)
		if client and row.user not in old and row.user not in allowed and not manager:
			frappe.throw(_("A client joins a project through an invitation."), frappe.PermissionError)


# --- sign-in ----------------------------------------------------------------------------------------------------


def refuse_client_without_project(login_manager=None):
	"""on_session_creation: a client with no project has nothing to open; refuse the sign-in with a plain message."""
	user = getattr(login_manager, "user", None) or frappe.session.user
	if not user or user in ("Guest", "Administrator") or not is_client(user):
		return
	if frappe.db.exists("Project Member", {"parenttype": "Construction Project", "user": user}):
		return
	from construction_core.accounts.sessions import _refuse

	try:
		_refuse(getattr(frappe.local, "session_obj", None) and frappe.local.session_obj.sid)
	except frappe.AuthenticationError:
		# frappe.throw puts the words in _server_messages, which Frappe's login page shows instead of its default
		frappe.throw(_("You don't have access to any project yet. Contact the team that invited you."),
			frappe.AuthenticationError)
