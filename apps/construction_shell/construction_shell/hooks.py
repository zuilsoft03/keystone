app_name = "construction_shell"
app_title = "Keystone"  # the product's name (D-298); app_publisher and the app names stay internal
app_publisher = "Construction Workspace"
app_description = "The staff workspace and the client portal: a Vue 3 + frappe-ui single-page app on construction_core"
app_email = "maintainers@construction-workspace.invalid"
app_license = "agpl-3.0"

# The shell depends on the core and never the reverse (PLAN §5.3, dev/check-deps.sh). No ERPNext (D-104).
required_apps = ["construction_core"]

# The one entry from Desk (ARCHITECTURE §3.3, D-113): the apps screen reads this hook, and setup.py keeps exactly one
# Desktop Icon for sites that use the icon grid.
add_to_apps_screen = [
	{
		"name": "construction_shell",
		"logo": "/assets/construction_shell/icon-192.png",  # the app icon: mark B, dark tone, on Ink (D-298)
		"title": "Keystone",
		"route": "/workspace",
		"has_permission": "construction_shell.api.can_open_workspace",
	}
]

# D-067, D-108, DR-3: the shell claims the whole /workspace namespace, so no sub-path ends in Frappe's HTTP 500 for the
# Workspace DocType. The catch-all carries /<project>/<section>/... (measured form, S10-a); a third, narrower rule
# would only overlap it. Every path ends in ws_workspace, which renders the app or our own 404.
# A route rule change is a deploy event (DR-2): deploy/init-site.sh clears the caches (construction_shell.deploy).
website_route_rules = [
	{"from_route": "/workspace", "to_route": "ws_workspace"},
	{"from_route": "/workspace/<path:app_path>", "to_route": "ws_workspace"},
]

after_install = "construction_shell.setup.after_install"

# P2-05 (D-120): the tools' Desk forms open them in the workspace.
doctype_js = {
	"Whiteboard": "public/js/desk_links.js",
	"CAD Drawing": "public/js/desk_links.js",
	"File": "public/js/desk_links.js",
	"Project Document": "public/js/desk_links.js",
}

# P2-06 (D-121): the client portal presented by the shell's portal app. construction_core keeps the /portal routes and
# every check; it calls this only after its own gates, and site config cc_portal_spa = 0 keeps its server-rendered page.
cc_portal_renderer = "construction_shell.portal.render"
cc_join_renderer = "construction_shell.join.render"  # P3-17 (D-214): the join page's app, after core's own page
cc_login_renderer = "construction_shell.login.render"  # P3-24 (D-251): /login and /update-password as LoginA
cc_mailbox_renderer = "construction_shell.mailbox.render"  # P3-77: the evidence mailbox's confirm page
cc_dispute_renderer = "construction_shell.mailbox.render_dispute"  # P3-78: a receipt's "This was not me" page
