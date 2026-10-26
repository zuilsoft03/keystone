"""The client portal's presenter (P2-06, D-121): construction_core's /portal page calls `render` (hook
cc_portal_renderer) only after its own checks have passed: a signed-in client, and a project or board they may read.

It returns the portal app's files and the boot data, or None (the app is not built), and the page then stays
server-rendered. It adds no access: the app reads construction_core.portal_api and discuss.api, which check every call.
"""

import frappe

from construction_shell.preferences import mode_of
from construction_shell.workspace_page import brand_boot, shell_assets, tab_title

ENTRY = "src/portal.js"


def render(context) -> dict | None:
	assets = shell_assets(ENTRY)
	if not assets:
		return None
	user = frappe.session.user
	context.title = tab_title(context.get("title"))  # "Page · Product name" (D-299); the core's page shows this title
	return {
		**assets,
		"boot": {
			"user": user,
			"full_name": frappe.utils.get_fullname(user),
			"email": frappe.get_cached_value("User", user, "email") or user,
			"user_image": frappe.get_cached_value("User", user, "user_image") or "",
			"sitename": frappe.local.site,
			**brand_boot(),
			"view": context.get("view"),
			"mode": mode_of(user),  # the client's own Simple or Advanced view (D-154, D-163)
		},
	}
