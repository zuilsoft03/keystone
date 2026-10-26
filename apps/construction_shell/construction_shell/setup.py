"""Install steps of the shell (P2-02): exactly one Desktop Icon for the workspace (ARCHITECTURE §3.3, D-113)."""

import frappe

from construction_shell import hooks

ICON_LABEL = hooks.app_title  # Frappe names an app's icon after its app_title, so this is that one value (D-298)
ICON_ROLES = ("Construction Staff", "Construction Manager", "System Manager")


def after_install():
	ensure_desktop_icon()
	frappe.clear_cache()  # DR-2: the new route rules take effect at once


def ensure_desktop_icon():
	"""One Desktop Icon that links out to /workspace, for sites on the icon grid; the apps screen uses the hook.

	Idempotent. Frappe names an app's icon after its app_title, so its own seeding finds this one and adds none.
	Not `standard`: a standard icon is exported into the app folder in developer mode."""
	others = frappe.get_all("Desktop Icon", filters={"link": "/workspace", "name": ["!=", ICON_LABEL]}, pluck="name")
	for name in others:
		frappe.delete_doc("Desktop Icon", name, ignore_permissions=True, force=True)
	if frappe.db.exists("Desktop Icon", ICON_LABEL):
		icon = frappe.get_doc("Desktop Icon", ICON_LABEL)
	else:
		icon = frappe.new_doc("Desktop Icon")
		icon.label = ICON_LABEL
	icon.update(
		{
			"icon_type": "App",
			"app": "construction_shell",
			"link_type": "External",
			"link": "/workspace",
			"logo_url": "/assets/construction_shell/icon-192.png",  # the app icon (brand.md), as the hook's logo
			"standard": 0,
			"hidden": 0,
		}
	)
	icon.set("roles", [{"role": r} for r in ICON_ROLES if frappe.db.exists("Role", r)])
	icon.save(ignore_permissions=True)
