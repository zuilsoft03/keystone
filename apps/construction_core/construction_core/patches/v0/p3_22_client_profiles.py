"""P3-22 (R-13; D-212, D-239): every client account has a Client Profile; one made here records no consent."""

import frappe
from frappe.utils import get_fullname, today

from construction_core.permissions import CLIENT_ROLE


def execute():
	clients = frappe.get_all("Has Role", filters={"role": CLIENT_ROLE, "parenttype": "User"}, pluck="parent",
		distinct=True)
	for user in clients:
		if frappe.db.exists("Client Profile", {"account": user}):
			continue
		member = frappe.db.exists("Project Member", {"parenttype": "Construction Project", "user": user})
		frappe.get_doc({"doctype": "Client Profile", "account": user, "full_name": get_fullname(user),
			"left_on": None if member else today()}).insert(ignore_permissions=True)  # no consent: none was given
