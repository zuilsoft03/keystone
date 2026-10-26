"""Idempotent setup, run from after_install and from a post-model-sync patch (so existing sites get it too)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CLIENT_ROLE = "Construction Client"

# D-086: our File fields are prefixed `cc_` so they never clash with Drive's own File fields.
CUSTOM_FIELDS = {
	"File": [
		{
			"fieldname": "cc_project",
			"label": "Project (Construction)",
			"fieldtype": "Link",
			"options": "Construction Project",
			"insert_after": "folder",
			"search_index": 1,
			"ignore_user_permissions": 1,  # never auto-filled from a default User Permission (D-086)
		},
		{
			"fieldname": "cc_client_visible",
			"label": "Client Visible",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "cc_project",
		},
		{
			# StorageProvider.delete trashes, never hard-deletes (ARCHITECTURE §2.6).
			"fieldname": "cc_trashed",
			"label": "Trashed",
			"fieldtype": "Check",
			"default": "0",
			"read_only": 1,
			"insert_after": "cc_client_visible",
		},
		{
			# P1-17: the ONLYOFFICE session key, kept for a whole editing session (office.api.document_key).
			"fieldname": "cc_office_key",
			"label": "Office Session Key",
			"fieldtype": "Data",
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
			"insert_after": "cc_trashed",
		},
		# P3-43 (D-301): file versions. Set only by the system (files.versions, permissions.validate_file).
		{
			# On a version row: the working file it is an earlier revision of. Such rows leave every list.
			"fieldname": "cc_version_of",
			"label": "Version Of",
			"fieldtype": "Link",
			"options": "File",
			"read_only": 1,
			"no_copy": 1,
			"search_index": 1,
			"ignore_user_permissions": 1,
			"insert_after": "cc_office_key",
		},
		{
			# The revision letter: on a working file its current one (empty is A), on a version row the one it holds.
			"fieldname": "cc_rev",
			"label": "Revision",
			"fieldtype": "Data",
			"length": 8,
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "cc_version_of",
		},
		{
			"fieldname": "cc_rev_by",
			"label": "Revision By",
			"fieldtype": "Link",
			"options": "User",
			"read_only": 1,
			"no_copy": 1,
			"ignore_user_permissions": 1,
			"insert_after": "cc_rev",
		},
		{
			"fieldname": "cc_rev_on",
			"label": "Revision On",
			"fieldtype": "Datetime",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "cc_rev_by",
		},
		{
			"fieldname": "cc_rev_note",
			"label": "What Changed",
			"fieldtype": "Small Text",
			"read_only": 1,
			"no_copy": 1,
			"ignore_xss_filter": 1,  # always shown as text ({{ }}); Frappe's filter would escape it on every save
			"insert_after": "cc_rev_on",
		},
	],
	"User": [
		{
			# P3-13 (D-202): when the account was last turned off or on; a session started before it is refused.
			"fieldname": "cc_access_stamp",
			"label": "Access Changed",
			"fieldtype": "Datetime",
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
			"permlevel": 1,  # System Manager level: never written through a user's share of their own record
			"insert_after": "enabled",
		},
	],
}

# What the client role may read by role (D-087); permissions.CLIENT_READABLE also covers File, which the client
# reads through Frappe's own File rules plus ours. More doctypes are added by the slices that create them.
CLIENT_READ = ["Construction Project", "Project Document", "RFI", "Submittal", "Variation Order",
	"Approval Request"]  # P3-76: a request only through its own rule (approvals.read)


# Action-level permissions (ARCHITECTURE §2.4, D-028): a Permission Type per action, granted to roles through
# Custom DocPerm, so it is visible and editable in the Role Permission Manager.
PERMISSION_TYPES = [
	("BOQ", "approve_boq", ["Construction Manager"]),
	("Submittal", "approve_submittal", ["Construction Manager"]),
	("Variation Order", "approve_variation", ["Construction Manager"]),
	("Construction Project", "manage_clients", ["Construction Manager"]),  # P1-13: clients.add_client
	# P3-77 (approvals design §3.4, D-429): sending a request, and recording a paper approval (P3-78), per project
	("Construction Project", "request_client_approval", ["Construction Manager"]),
	("Construction Project", "record_paper_approval", ["Construction Manager"]),
]

# Records that carry decisions are not deleted by Construction Staff (P1-08 audit). The JSON says so too, but the
# Custom DocPerm rows created above replace a doctype's standard permissions, so the rule is applied there as well.
NO_DELETE = [(dt, "Construction Staff") for dt in ("BOQ", "RFI", "Submittal", "Variation Order")]
# P3-76 (D-427): approval records are never deleted (their controllers refuse it too, for every user)
NO_DELETE += [(dt, role) for dt in ("Approval Request", "Approval Event", "Approval Evidence Detail")
	for role in ("System Manager", "Construction Manager", "Construction Staff", CLIENT_ROLE)]

# P3-40 (D-288): a project's permlevel-2 fields (the site and the internal money fields) are changed by managers only;
# Construction Staff read them. The JSON says so too; the Custom DocPerm rows replace it on a site that has them.
READ_ONLY_LEVELS = [("Construction Project", "Construction Staff", 2)]


def after_install():
	setup()
	from construction_core.accounts.sessions import ensure_user_index

	ensure_user_index()  # P3-67 gate: ending an account's sessions must not scan every session


# Our own roles (D-104): never ERPNext's Projects Manager / Projects User, which grant rights on ERPNext doctypes.
MANAGER_ROLE, STAFF_ROLE = "Construction Manager", "Construction Staff"


def before_install():
	ensure_roles()


def setup():
	ensure_roles()
	ensure_client_role()
	create_custom_fields(CUSTOM_FIELDS, update=True)
	for doctype in CLIENT_READ:
		ensure_read_perm(doctype, CLIENT_ROLE)
	ensure_permission_types()
	ensure_team_setup()
	ensure_no_delete()
	ensure_read_only_levels()
	repair_shared_folders()
	from construction_core.backups import ensure_defaults

	ensure_defaults()  # P2-01: the off-host copy setting starts on, 30 days
	from construction_core.workspace import ensure_default_template

	ensure_default_template()
	from construction_core.accounts.sessions import pin_session_expiry

	pin_session_expiry()  # P3-13 (D-197)
	from construction_core.accounts import guard, settings

	guard.apply_property_setters()  # P3-14 (D-204)
	settings.apply()
	from construction_core.accounts.visibility import restrict_contacts

	restrict_contacts()  # P3-15 (D-206)
	from construction_core.accounts import two_step

	two_step.setup()  # P3-20 (D-227): the opt-in role and the site switch; nobody affected until they opt in
	from construction_core.accounts.setup import seed_privacy

	seed_privacy()  # P3-51 (D-344): init-site.sh's privacy contact pre-fills the wizard's W1
	frappe.clear_cache()


def ensure_roles():
	for role in (MANAGER_ROLE, STAFF_ROLE):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_client_role():
	if not frappe.db.exists("Role", CLIENT_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": CLIENT_ROLE, "desk_access": 0}).insert(
			ignore_permissions=True
		)
	else:
		frappe.db.set_value("Role", CLIENT_ROLE, "desk_access", 0)


def ensure_read_perm(doctype: str, role: str):
	"""Grant read (permlevel 0) through Custom DocPerm, the way the Role Permission Manager does."""
	from frappe.permissions import add_permission

	add_permission(doctype, role, 0)
	set_perm(doctype, role, 0, "read", 1)


def set_perm(doctype: str, role: str, level: int, ptype: str, value: int):
	"""Frappe's update_permission_property, only when the stored value differs: a setup that changes nothing saves
	no Custom DocPerm, so it runs outside a patch too (a ledger doctype's rows are saved only under setup, P3-76)."""
	from frappe.permissions import update_permission_property

	if frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": level}, ptype) != value:
		update_permission_property(doctype, role, level, ptype, value)


def ensure_permission_types(types=PERMISSION_TYPES):
	from frappe.permissions import add_permission, update_permission_property

	for doctype, ptype, roles in types:
		if not frappe.db.exists("DocType", doctype):
			continue  # the slice that creates the doctype runs setup again
		if not frappe.db.exists("Permission Type", {"doc_type": doctype, "perm_type": ptype}):
			frappe.get_doc({"doctype": "Permission Type", "doc_type": doctype, "perm_type": ptype}).insert(
				ignore_permissions=True
			)
		for role in roles:
			add_permission(doctype, role, 0)
			update_permission_property(doctype, role, 0, ptype, 1)


# P3-56 (QD, QE; S3's block): a team account's job title, seen by the team only and written by System Managers
# (permlevel 1); a project's Team, changed by its Construction Managers and System Managers (projects_team).
TEAM_FIELDS = {"User": [{"fieldname": "cc_job_title", "label": "Job Title", "fieldtype": "Data", "length": 140,
	"permlevel": 1, "insert_after": "cc_access_stamp"}]}
TEAM_PERMISSION_TYPES = [("Construction Project", "manage_team", ["Construction Manager", "System Manager"])]


def ensure_team_setup():
	create_custom_fields(TEAM_FIELDS, update=True)
	ensure_permission_types(TEAM_PERMISSION_TYPES)


def ensure_no_delete():
	for doctype, role in NO_DELETE:
		if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
			set_perm(doctype, role, 0, "delete", 0)


def ensure_read_only_levels():
	for doctype, role, level in READ_ONLY_LEVELS:
		if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": level}):
			set_perm(doctype, role, level, "write", 0)


def repair_shared_folders():
	"""Folders above Projects/<project> are shared: they belong to no project (P1-11 exit audit)."""
	from construction_core.providers.storage import PROJECTS_ROOT

	for name in frappe.get_all("File", filters={"is_folder": 1, "folder": "Home", "file_name": PROJECTS_ROOT},
			pluck="name"):
		# A stamped folder was also forced private (permissions.force_private), which hid it from staff.
		frappe.db.set_value("File", name, {"cc_project": None, "cc_client_visible": 0, "is_private": 0},
			update_modified=False)

