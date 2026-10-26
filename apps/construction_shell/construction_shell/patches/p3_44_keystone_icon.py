"""P3-44 (D-298, D-400): the workspace's one Desktop Icon is named after the app, Keystone.

A site installed before the rename holds a "Construction Workspace" icon. `ensure_desktop_icon` keeps one icon for the
workspace under the app's title and removes any other that links to it, so after this patch an existing site has
the Keystone icon (with the app icon as its logo) and no old one. A person's saved icon grid (Desktop Layout) names
icons by label, so the old label in it becomes the new one and the tile stays. It changes nothing on a second run."""

import json

import frappe

from construction_shell import setup

OLD_LABEL = "Construction Workspace"


def execute():
	setup.ensure_desktop_icon()
	rename_in_saved_layouts(OLD_LABEL, setup.ICON_LABEL)


def rename_in_saved_layouts(old: str, new: str):
	"""Every string in a saved layout that is exactly the old label (an icon's label, or a child's parent_icon)
	becomes the new one. A layout that holds no old label, or that is not JSON, is left as it is."""
	if not frappe.db.exists("DocType", "Desktop Layout"):
		return
	for name, layout in frappe.get_all("Desktop Layout", fields=["name", "layout"], as_list=True):
		if not layout or old not in layout:
			continue
		try:
			saved = json.loads(layout)
		except ValueError:
			continue
		renamed = _renamed(saved, old, new)
		if renamed != saved:
			frappe.db.set_value("Desktop Layout", name, "layout", json.dumps(renamed), update_modified=False)


def _renamed(value, old, new):
	if isinstance(value, str):
		return new if value == old else value
	if isinstance(value, list):
		return [_renamed(v, old, new) for v in value]
	if isinstance(value, dict):
		return {_renamed(k, old, new): _renamed(v, old, new) for k, v in value.items()}
	return value
