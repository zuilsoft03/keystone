"""/approval-dispute, the "This was not me" page of an approval receipt (P3-78, approvals design §3.7, M11), a
sign-in-free page like /evidence-mailbox.

It serves no data, and opening it records nothing (a mail scanner's GET included): the link's token is in the URL
fragment, which never reaches this server. The page posts it to construction_core.approvals.dispute.view, which says what
was answered, and on the person's click to dispute.not_me. An installed presenter (hook ``cc_dispute_renderer``) draws
it as the shell's app, with the brand and both themes; without one, the plain template renders.
"""

import frappe

no_cache = 1


def get_context(context):
	context.title = "This was not me"
	context.no_breadcrumbs = 1
	hooks = frappe.get_hooks("cc_dispute_renderer")
	spa = frappe.get_attr(hooks[-1])(context) if hooks else None
	if isinstance(spa, dict) and isinstance(spa.get("script"), str) and isinstance(spa.get("styles"), list) \
			and isinstance(spa.get("boot"), dict):
		context.spa = spa
		context.spa_base = "construction_core/templates/cc_spa.html"
		# an approver signed in on this browser posts with their session's token; a guest's call needs none
		context.csrf_token = frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else ""
	return context
