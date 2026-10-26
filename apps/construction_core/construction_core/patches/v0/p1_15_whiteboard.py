"""P1-15: existing Workspace Configs get the "whiteboards" portal section (on), like new ones."""

import frappe


def execute():
	for cfg in frappe.get_all("Workspace Config", pluck="name"):
		if not frappe.db.exists("Workspace Section", {"parenttype": "Workspace Config", "parent": cfg, "section": "whiteboards"}):
			doc = frappe.get_doc("Workspace Config", cfg)
			doc.append("sidebar_sections", {"section": "whiteboards", "visible": 1, "client_visible": 1})
			doc.flags.cc_system = True
			doc.save(ignore_permissions=True)
