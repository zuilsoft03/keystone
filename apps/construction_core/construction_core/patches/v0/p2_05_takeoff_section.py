"""P2-05: every project's rail gains the takeoff section (staff only), after the whiteboards, as new projects get it."""

import frappe


def execute():
	for name in frappe.get_all("Workspace Config", pluck="name"):
		config = frappe.get_doc("Workspace Config", name)
		sections = [s.section for s in config.sidebar_sections]
		if "takeoff" in sections:
			continue
		at = sections.index("whiteboards") + 1 if "whiteboards" in sections else len(sections)
		rows = [s.as_dict() for s in config.sidebar_sections]
		rows.insert(at, {"section": "takeoff", "visible": 1, "client_visible": 0})
		config.set("sidebar_sections", [])
		for row in rows:
			config.append("sidebar_sections", {k: row[k] for k in ("section", "visible", "client_visible")})
		# ignore_permissions: the rail is provisioned by the system, as at project creation (workspace.create_workspace).
		config.save(ignore_permissions=True)
