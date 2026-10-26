"""/join, the sign-in-free join page (P3-17, R-13; D-187, D-214).

It serves no data: the link's token is in the URL fragment, which never reaches this server; the page posts it to
construction_core.onboarding.join, which checks the invitation on every call. `/join` itself is the page; every path
below it ends in our own 404 (DR-3). An installed presenter (hook ``cc_join_renderer``) draws the page as the shell's
join app; without one, the page tells the person to open the link in a browser that runs it.
"""

import frappe

no_cache = 1


def get_context(context):
	request = getattr(frappe.local, "request", None)
	path = (request.path if request else "/join").rstrip("/") or "/"
	context.title = "Join your project"
	context.no_breadcrumbs = 1
	if path != "/join":
		context.view = "not_found"
		context.title = "Not found"
		context.http_status_code = 404
		return context
	context.view = "join"
	hooks = frappe.get_hooks("cc_join_renderer")
	spa = frappe.get_attr(hooks[-1])(context) if hooks else None
	if isinstance(spa, dict) and isinstance(spa.get("script"), str) and isinstance(spa.get("styles"), list) \
			and isinstance(spa.get("boot"), dict):
		context.spa = spa
		context.spa_base = "construction_core/templates/cc_spa.html"
		context.csrf_token = ""  # a guest's page: the join calls need none
	return context
