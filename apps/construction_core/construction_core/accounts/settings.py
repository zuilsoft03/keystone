"""P3-14 (R-13; D-197, D-204): the sign-in and account settings this app relies on, pinned.

`apply()` runs at install, in the P3-14 patch and after every migrate, so neither a Frappe upgrade that re-syncs its
standard web forms nor a change in Desk leaves a door open. `deviations()` lists what differs; the tests (and later
the go-live check) use it.
"""

import frappe
from frappe.utils import cint

SYSTEM = {
	"login_with_email_link": 0,  # the mailbox alone would sign in, and it skips two-step sign-in
	"allow_login_using_mobile_number": 0,
	"allow_login_using_user_name": 0,
	"logout_on_password_reset": 1,
	"allow_guests_to_upload_files": 0,
	"bypass_2fa_for_retricted_ip_users": 0,
	"bypass_restrict_ip_check_if_2fa_enabled": 0,
	"enable_password_policy": 1,
}
WEBSITE = {
	"disable_signup": 1,  # accounts come only from invitations (R-13)
	"auto_account_deletion": 0,  # a deletion request is reviewed by a person, never run unattended after 72 h
}
MIN_PASSWORD_SCORE = 2
# Frappe's standard web forms that write account data with ignore_permissions (P3-13 review W5): rights requests go
# to the privacy contact by email instead (D-197).
WEB_FORMS = ("edit-profile", "request-data", "request-to-delete-data")


def apply():
	for field, value in SYSTEM.items():
		frappe.db.set_single_value("System Settings", field, value)
	if cint(frappe.db.get_single_value("System Settings", "minimum_password_score")) < MIN_PASSWORD_SCORE:
		frappe.db.set_single_value("System Settings", "minimum_password_score", str(MIN_PASSWORD_SCORE))
	for field, value in WEBSITE.items():
		frappe.db.set_single_value("Website Settings", field, value)
	for name in WEB_FORMS:
		if frappe.db.exists("Web Form", name):
			frappe.db.set_value("Web Form", name, "published", 0, update_modified=False)
	frappe.clear_cache()


def deviations() -> list[str]:
	out = [f"System Settings.{f}" for f, v in SYSTEM.items()
		if cint(frappe.db.get_single_value("System Settings", f)) != v]
	if cint(frappe.db.get_single_value("System Settings", "minimum_password_score")) < MIN_PASSWORD_SCORE:
		out.append("System Settings.minimum_password_score")
	out += [f"Website Settings.{f}" for f, v in WEBSITE.items()
		if cint(frappe.db.get_single_value("Website Settings", f)) != v]
	out += [f"Web Form {n}" for n in WEB_FORMS if cint(frappe.db.get_value("Web Form", n, "published"))]
	return out
