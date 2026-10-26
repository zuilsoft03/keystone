"""P1-20 audit (D-104): remove what the old setup put on ERPNext's doctypes, now that the core no longer uses them.

- Custom DocPerm on ERPNext's Project (a copy of its standard rights plus our client read and Desk User levels):
  ERPNext's Project has no predicate of ours any more, so a client read there would list every ERPNext project.
  Deleting the copy restores ERPNext's own rights. Any other grant to our roles outside our module goes too.
- Our Custom Fields and Property Setters on Project, Project User, Task and Location.
- ERPNext's project roles, from users who now hold ours.
"""

import frappe

ERP = ("Project", "Project User", "Task", "Location")
OURS_ROLES = ("Construction Client", "Construction Staff", "Construction Manager")
OLD_ROLES = {"Projects Manager": "Construction Manager", "Projects User": "Construction Staff"}


def execute():
	ours = set(frappe.get_all("DocType", filters={"module": "Construction Core"}, pluck="name"))
	for row in frappe.get_all("Custom DocPerm", fields=["name", "parent", "role", "permlevel"],
			filters={"parent": ["not in", list(ours)]}):
		if row.parent == "Project" or row.role in OURS_ROLES:
			frappe.db.delete("Custom DocPerm", row.name)
	for name in frappe.get_all("Custom Field", filters={"dt": ["in", ERP], "fieldname": ["like", "cc\_%"]}, pluck="name"):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
	for name in frappe.get_all("Property Setter", filters={"doc_type": ["in", ERP],
			"property": ["in", ["permlevel", "max_attachments", "ignore_user_permissions"]]}, pluck="name"):
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
	for old, new in OLD_ROLES.items():
		for user in frappe.get_all("Has Role", filters={"role": old, "parenttype": "User"}, pluck="parent"):
			if frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": new}):
				frappe.db.delete("Has Role", {"parent": user, "parenttype": "User", "role": old})
				frappe.clear_cache(user=user)
	frappe.clear_cache()
