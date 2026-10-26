"""P3-65 (design §3.2, FIT-13): every project with a folder tree gets the internal "Discussion files" folder, where the
Team room's files land. New projects get it on first use (discuss.media.materialize); the Folder Template is not
changed, so a set-up edit cannot remove it."""

import frappe

from construction_core.providers.storage import INTERNAL_CHAT, PROJECTS_ROOT, ROOT, get_storage
from construction_core.workspace import root_path


def execute():
	projects_folder = frappe.db.get_value("File", {"is_folder": 1, "folder": ROOT, "file_name": PROJECTS_ROOT}, "name")
	if not projects_folder:
		return
	store = get_storage()
	for project in frappe.get_all("Construction Project", pluck="name"):
		if frappe.db.exists("File", {"is_folder": 1, "folder": projects_folder, "file_name": project}):
			store.ensure_path(f"{root_path(project)}/{INTERNAL_CHAT}", project)
