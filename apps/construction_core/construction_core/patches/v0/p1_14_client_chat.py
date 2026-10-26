"""P1-14: existing Workspace Configs get the "documents" portal section (on), like new ones."""

import frappe


def execute():
	for cfg in frappe.get_all("Workspace Config", pluck="name"):
		if not frappe.db.exists("Workspace Section", {"parenttype": "Workspace Config", "parent": cfg, "section": "documents"}):
			doc = frappe.get_doc("Workspace Config", cfg)
			doc.append("sidebar_sections", {"section": "documents", "visible": 1, "client_visible": 1})
			doc.flags.cc_system = True
			doc.save(ignore_permissions=True)
