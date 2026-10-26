# Copyright (c) 2026, Construction Workspace and contributors
"""Scan Hold (P3-75, D-417): a client's large Files send waiting for its background virus scan (scan_holds).
System Manager only; the client reads its own holds through portal_api.checking."""

from frappe.model.document import Document


class ScanHold(Document):
	pass


def on_doctype_update():
	from frappe import db

	db.add_index("Scan Hold", ["project", "uploader", "state"], "project_uploader_state")
	db.add_index("Scan Hold", ["state", "next_try"], "state_next_try")
