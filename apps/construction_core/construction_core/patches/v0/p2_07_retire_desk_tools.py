"""P2-07 (D-120, D-124): the Desk tool pages are retired; the workspace hosts the whiteboard, the takeoff and the office
editor. Frappe keeps a Page record whose folder is gone, so the records are deleted here."""

import frappe


def execute():
	for page in ("board", "drawing-takeoff", "office-editor"):
		if frappe.db.exists("Page", page):
			frappe.delete_doc("Page", page, force=True, ignore_permissions=True)
