"""The sign-in page's presenter (P3-24, D-251, D-252). construction_core's /login and /update-password pages call it
(hook cc_login_renderer); it returns the shell's sign-in app and what the page shows before anyone signs in: the
product's and the company's names (D-298, D-210), the help contact, whether the visitor is already signed in (the
password page), and for the clients' look the sign-in pictures a manager marked, by id and caption only (P3-34,
D-273)."""

import frappe

from construction_core.onboarding import privacy
from construction_shell.workspace_page import brand_boot, shell_assets, tab_title

ENTRY = "src/login.js"


def render(context, view="login") -> dict | None:
	assets = shell_assets(ENTRY)
	if not assets:
		return None
	context.title = tab_title(context.get("title"))  # "Page · Product name" (D-299)
	signed_in = frappe.session.user != "Guest"
	look = context.get("cc_look") if context.get("cc_look") in ("team", "client") else "team"
	boot = {"view": view, "look": look, **brand_boot(), "signed_in": signed_in,
		"help_email": privacy.contact(),
		"email": (frappe.session.user if signed_in else "")}
	if look == "client":  # P3-34 (D-273): the marked renders behind LoginB, by id and caption only
		from construction_core.signin_pictures import for_signin

		boot["pictures"] = for_signin(frappe.form_dict.get("redirect-to"))
	return {**assets, "boot": boot}
