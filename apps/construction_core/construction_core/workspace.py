"""Project workspace setup (P1-05; ARCHITECTURE §6.2-§6.4, D-071, D-079).

A Project with a workspace starts at contract signature (D-071), so it needs ``cc_contract_signed_on``. When it is
created, its Workspace Config and its folder tree (from a Folder Template, through ``StorageProvider``) are created
idempotently; the folder ids are stored in Workspace Config.
"""

import json

import frappe
from frappe import _

from construction_core.providers.storage import CLIENT_CHAT, CLIENT_INBOX, PROJECTS_ROOT, get_storage

DEFAULT_TEMPLATE = "Standard"
STANDARD_FOLDERS = [
	("01_Contract", 0),
	("02_Design/Drawings", 0),
	("02_Design/Specifications", 0),
	("03_RFI", 0),
	("04_Submittals", 0),
	("05_Site", 0),
	("06_Client", 1),
	("07_Closeout", 0),
]
DEFAULT_SECTIONS = [
	("home", 1, 1),
	("files", 1, 1),
	("documents", 1, 1),
	("rfi", 1, 1),
	("submittals", 1, 1),
	("variations", 1, 1),
	("discuss", 1, 1),
	("approvals", 1, 0),  # P3-76: off for clients until the team turns approvals on (permissions.DEFAULT_OFF)
	("whiteboards", 1, 1),
	("takeoff", 1, 0),  # P2-05: the DXF and PDF takeoff in the workspace, staff only
	("boq", 1, 0),
	("settings", 1, 0),
]


def root_path(project: str) -> str:
	return f"{PROJECTS_ROOT}/{project}"


def ensure_default_template():
	if frappe.db.exists("Folder Template", DEFAULT_TEMPLATE):
		return
	frappe.get_doc(
		{
			"doctype": "Folder Template",
			"template_name": DEFAULT_TEMPLATE,
			"folders": [{"path": p, "client_visible": v} for p, v in STANDARD_FOLDERS],
		}
	).insert(ignore_permissions=True)


def validate_project(doc, method=None):
	"""Project.validate: a workspace project starts at contract signature (D-071)."""
	if doc.get("cc_workspace_enabled") and not doc.get("cc_contract_signed_on"):
		frappe.throw(_("Enter the contract signature date: a project starts at contract signature."),
			title=_("Contract not signed"))


def on_project_insert(doc, method=None):
	if doc.get("cc_workspace_enabled"):
		create_workspace(doc.name)


def create_workspace(project: str) -> str:
	"""Create or complete the project's Workspace Config and folder tree. Safe to call again."""
	ensure_default_template()
	template_name = frappe.db.get_value("Construction Project", project, "cc_folder_template") or DEFAULT_TEMPLATE
	template = frappe.get_doc("Folder Template", template_name)
	store = get_storage()

	folders = {"": store.ensure_path(root_path(project), project)}
	for row in template.folders:
		fid = store.ensure_path(f"{root_path(project)}/{row.path}", project)
		folders[row.path] = fid
		if row.client_visible:
			# The folder and its parents up to the project root are visible to the project's clients.
			_mark_client_visible(fid, stop=folders[""])
	_mark_client_visible(folders[""], stop=None)
	folders = ensure_client_folders(project, folders)

	if frappe.db.exists("Workspace Config", project):
		cfg = frappe.get_doc("Workspace Config", project)
	else:
		cfg = frappe.get_doc({"doctype": "Workspace Config", "project": project, "folder_template": template_name})
		for section, visible, client_visible in DEFAULT_SECTIONS:
			cfg.append("sidebar_sections", {"section": section, "visible": visible, "client_visible": client_visible})
	cfg.folders = json.dumps(folders, sort_keys=True)
	cfg.flags.cc_system = True  # the folder map is server-set (WorkspaceConfig.validate)
	# ignore_permissions: the workspace is provisioned by the system when its Project is created.
	cfg.save(ignore_permissions=True) if not cfg.is_new() else cfg.insert(ignore_permissions=True)
	return cfg.name


def _mark_client_visible(folder: str, stop: str | None):
	while folder:
		frappe.db.set_value("File", folder, "cc_client_visible", 1, update_modified=False)
		if folder == stop:
			break
		parent = frappe.db.get_value("File", folder, "folder")
		if not parent or parent == "Home" or stop is None:
			break
		folder = parent


def folder_for(project: str, path: str) -> str | None:
	raw = frappe.db.get_value("Workspace Config", project, "folders")
	return json.loads(raw).get(path) if raw else None


def client_folders(project: str) -> dict[str, str | None]:
	"""The folders a client's files land in (P3-07, D-158): ``inbox`` for Files, ``chat`` for conversations."""
	return {"inbox": folder_for(project, CLIENT_INBOX), "chat": folder_for(project, CLIENT_CHAT)}


def ensure_client_folders(project: str, folders: dict[str, str]) -> dict[str, str]:
	"""Add 06_Client and the two client folders to a project's tree and map, whatever its template (P3-07). The two
	folders are not shown to clients as folders: what a client sees of them is decided file by file (D-158)."""
	store = get_storage()
	folders = dict(folders)
	for path in ("06_Client", CLIENT_INBOX, CLIENT_CHAT):
		if path not in folders:
			folders[path] = store.ensure_path(f"{root_path(project)}/{path}", project)
	for path in (CLIENT_INBOX, CLIENT_CHAT):
		frappe.db.set_value("File", folders[path], "cc_client_visible", 0, update_modified=False)
	return folders
