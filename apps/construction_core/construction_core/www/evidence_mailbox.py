"""/evidence-mailbox, the page of the evidence mailbox's confirm link (P3-77, approvals design §3.2 item 3), a sign-in-free
page like /join.

It serves no data: the link's token is in the URL fragment, which never reaches this server; the button posts it to
construction_core.approvals.api.confirm_evidence_mailbox, which checks it. An installed presenter (hook
``cc_mailbox_renderer``) draws the page as the shell's app, with the brand and both themes; without one, the plain
template below renders.
"""

import frappe

no_cache = 1


def get_context(context):
	context.title = "Confirm the evidence mailbox"
	context.no_breadcrumbs = 1
	hooks = frappe.get_hooks("cc_mailbox_renderer")
	spa = frappe.get_attr(hooks[-1])(context) if hooks else None
	if isinstance(spa, dict) and isinstance(spa.get("script"), str) and isinstance(spa.get("styles"), list) \
			and isinstance(spa.get("boot"), dict):
		context.spa = spa
		context.spa_base = "construction_core/templates/cc_spa.html"
		# a signed-in person (a System Manager checking the link) posts with their session's token; a guest's call needs none
		context.csrf_token = frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else ""
	return context
