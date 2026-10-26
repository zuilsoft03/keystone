"""P3-14 (R-13; D-200, D-204): what a person may change about their own account.

Every user holds a write share on their own User record (Frappe's share_with_self), and many security fields sit at
permlevel 0, so before this slice a session could switch its account back on, change its password without the old
one, raise its session limit or set its own 2FA bypass (measured 2026-10-12). Here:

- `PROTECTED` fields move to permlevel 1 (Property Setters): a save by anyone but a System Manager keeps their
  stored values, whichever path it takes (form, REST, a share).
- A client may not change the name or picture the project team sees (`guard_client_identity`).
- A User record is shared only with its own user, except by a System Manager (`refuse_user_share`).
- Frappe's invitation and sign-up methods are refused (`refused` is not whitelisted), and so is any User Invitation
  insert. Frappe's `change_password` stays: for anyone but a System Manager it changes nothing, as `new_password` is
  protected; System Managers set passwords with it in Desk. People change their own on the update-password page,
  which asks for the old one.
- A client's picture cannot be set through a File attached to their own User either (`guard_identity_file`).
"""

import frappe
from frappe import _
from frappe.utils import cint

# `enabled` is not here: Frappe's own user search filters on it as staff, and a permlevel-1 field cannot be filtered on
# by them (P3-15, D-207). `guard_enabled` refuses its change instead, on every path.
PROTECTED = (
	"new_password", "simultaneous_sessions", "bypass_restrict_ip_check_if_2fa_enabled", "module_profile",
	"social_logins", "username", "send_welcome_email", "logout_all_sessions", "last_password_reset_date",
	# read-only on screen but not on the server: the sign-in record administrators read (P3-14 audit S2)
	"last_ip", "last_login", "last_active", "last_known_versions",
)
IDENTITY = ("first_name", "middle_name", "last_name", "user_image", "banner_image")
GUARDED_FORMS = ("edit-profile", "request-data", "request-to-delete-data")


def apply_property_setters():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for field in PROTECTED:
		make_property_setter("User", field, "permlevel", 1, "Int", validate_fields_for_doctype=False)
	frappe.db.delete("Property Setter", {"doc_type": "User", "field_name": "enabled", "property": "permlevel"})
	frappe.clear_cache(doctype="User")


def _is_manager(user: str) -> bool:
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def guard_enabled(doc, method=None):
	"""User before_validate: only a System Manager turns an account off or on (D-207), through a share too."""
	if doc.is_new() or frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install or _is_manager(
			frappe.session.user):
		return
	stored = frappe.db.get_value("User", doc.name, "enabled")
	if stored is not None and cint(doc.enabled) != cint(stored):
		frappe.throw(_("Only an administrator can turn an account off or on."), frappe.PermissionError)


def guard_client_identity(doc, method=None):
	"""User before_validate: a client keeps the name and picture the team set (staff see them, D-197)."""
	user = frappe.session.user
	if (doc.is_new() or user != doc.name or frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install
			or _is_manager(user)):
		return
	if frappe.db.get_value("User", doc.name, "user_type") != "Website User":
		return
	stored = frappe.db.get_value("User", doc.name, IDENTITY, as_dict=True) or {}
	if any((doc.get(f) or "").strip() != (stored.get(f) or "").strip() for f in IDENTITY):
		frappe.throw(_("Your name and picture are set by the project team."), frappe.PermissionError)


def guard_identity_file(doc, method=None):
	"""File validate: a File attached to a client's own User as a picture would set it with db.set_value when made public
	(Frappe's handle_is_private_changed), past every User hook (P3-14 review F1)."""
	user = frappe.session.user
	if (doc.attached_to_doctype != "User" or doc.attached_to_field not in IDENTITY or doc.attached_to_name != user
			or _is_manager(user) or frappe.db.get_value("User", user, "user_type") != "Website User"):
		return
	frappe.throw(_("Your name and picture are set by the project team."), frappe.PermissionError)


def refuse_rename(doc, method=None, old=None, new=None, merge=False):
	"""User before_rename: a login is renamed by a System Manager only. Frappe's rename asks only for write on the old
	record, which every user holds on their own through its self share (P3-14 audit M1)."""
	if frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install or _is_manager(frappe.session.user):
		return
	frappe.throw(_("Only an administrator can change a sign-in address."), frappe.PermissionError)


def refuse_client_api_key(doc, method=None):
	"""User validate (P3-78, approvals §4.5, T6): a client account never holds an API key, whatever saves it (Frappe's
	generate_keys, the form, REST, a script), so no client is ever signed in by a key. Read from the document's own
	roles and type: the role may arrive in this very save."""
	from construction_core.permissions import CLIENT_ROLE

	if doc.get("api_key") and (doc.user_type == "Website User" or CLIENT_ROLE in {r.role for r in doc.get("roles") or []}):
		frappe.throw(_("A client account cannot have an API key."), frappe.PermissionError)


def refuse_user_share(doc):
	"""Called from DocShare.validate: a User record is shared only with its own user (Frappe's self share)."""
	if doc.share_doctype != "User" or _is_manager(frappe.session.user):
		return
	if cint(doc.everyone) or doc.user != doc.share_name:
		frappe.throw(_("An account can be shared only with its own user."), frappe.PermissionError)


def remove_foreign_user_shares():
	for name in frappe.get_all("DocShare", filters={"share_doctype": "User"}, fields=["name", "user", "share_name",
			"everyone"]):
		if cint(name.everyone) or name.user != name.share_name:
			frappe.db.delete("DocShare", {"name": name.name})


@frappe.whitelist(allow_guest=True, methods=["POST", "PUT"])
def web_form_accept(web_form: str, data: str | dict, web_form_request_key: str | None = None):
	"""Frappe's web-form save, refused for the account and data-request forms even if a re-sync published them."""
	stored = frappe.db.get_value("Web Form", web_form, "name") or web_form  # names match case- and space-blind (S1)
	if str(stored).strip().lower() in GUARDED_FORMS:
		raise frappe.PermissionError(_("Not permitted"))
	from frappe.website.doctype.web_form.web_form import accept

	return accept(web_form, data, web_form_request_key)


def refused(*args, **kwargs):
	"""Frappe's invitation and sign-up methods (and a User Invitation insert) end here. Not whitelisted: every call is
	refused (D-204)."""
	raise frappe.PermissionError(_("Not permitted"))
