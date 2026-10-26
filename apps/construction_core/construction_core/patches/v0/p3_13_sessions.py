"""P3-13 (R-13, D-202): the User access stamp field, and sessions that end after 72 h without use."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from construction_core.accounts.sessions import pin_session_expiry
from construction_core.setup.install import CUSTOM_FIELDS


def execute():
	create_custom_fields({"User": CUSTOM_FIELDS["User"]}, update=True)
	pin_session_expiry()
