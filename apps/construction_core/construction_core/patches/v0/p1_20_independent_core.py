"""P1-20 (D-104): the core's own roles replace ERPNext's on this app's doctypes and pages.

Custom DocPerm rows (made by setup through the Role Permission Manager API) replace a doctype's JSON permissions,
so the rows that still name Projects Manager / Projects User are renamed. Users who held those roles get ours too.
ERPNext's Project records are not moved: no production data exists; dev data is reseeded in P1-21.
"""

import frappe

from construction_core.setup.install import MANAGER_ROLE, STAFF_ROLE, ensure_roles, setup

OLD = {"Projects Manager": MANAGER_ROLE, "Projects User": STAFF_ROLE}


def execute():
	ensure_roles()
	ours = set(frappe.get_all("DocType", filters={"module": "Construction Core"}, pluck="name"))
	for row in frappe.get_all("Custom DocPerm", filters={"role": ["in", list(OLD)]}, fields=["name", "parent", "role"]):
		if row.parent in ours:
			frappe.db.set_value("Custom DocPerm", row.name, "role", OLD[row.role], update_modified=False)
	for old, new in OLD.items():
		for user in frappe.get_all("Has Role", filters={"role": old, "parenttype": "User"}, pluck="parent"):
			if not frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": new}):
				u = frappe.get_doc("User", user)
				u.append("roles", {"role": new})
				u.save(ignore_permissions=True)
	setup()
