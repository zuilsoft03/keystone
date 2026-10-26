"""A person's view preference (P3-01, D-154): Simple or Advanced, kept on the server per user in frappe.defaults.

A view choice only: it changes which sections the screens list and which words they use, never what the server
returns or allows. Simple is the default, and anything stored other than exactly "advanced" reads as Simple, because
any signed-in user can write their own defaults through Frappe's own calls.
"""

import frappe
from frappe import _

from construction_core.portal_preview import client_of
from construction_shell.words import ADVANCED, SIMPLE, normal

VIEW_MODE = "cc_view_mode"  # frappe.defaults, per user, like cc_last_project (ARCHITECTURE §3.4)


def mode_of(user: str) -> str:
	return normal(frappe.defaults.get_user_default(VIEW_MODE, user=user))


@frappe.whitelist(methods=["POST"])
def set_mode(mode: str) -> str:
	"""Set the caller's own mode, staff or client (DR-5: the check is here). There is no user argument: a person
	changes only their own view."""
	user = frappe.session.user
	if user == "Guest":
		raise frappe.PermissionError(_("Sign in to change your view."))
	if mode not in (SIMPLE, ADVANCED):
		frappe.throw(_("Choose Simple or Advanced."))
	frappe.defaults.set_user_default(VIEW_MODE, mode, user=user)
	return mode


@frappe.whitelist(methods=["GET"])
def client_mode(project: str, contact: str) -> str:
	"""One client contact's Simple or Advanced view, for the staff preview of their portal (P3-05, D-136). The core's
	resolver checks the caller and that the row is this project's client (DR-5); there is no user argument, and the
	core never reads this shell key (rule 3d)."""
	return mode_of(client_of(project, contact))
