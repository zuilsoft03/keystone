"""P1-18: drawings made before PDF takeoff are DXF drawings."""

import frappe


def execute():
	frappe.db.sql("update `tabCAD Drawing` set source = %s where ifnull(source, %s) = %s", ("DXF", "", ""))
