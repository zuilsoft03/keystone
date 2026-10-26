# Copyright (c) 2026, Construction Workspace and contributors
"""Whiteboard Version: one append-only snapshot per save (P1-15). Staff read it; clients never do."""

import frappe
from frappe import _
from frappe.model.document import Document

from construction_core.permissions import _bypass


class WhiteboardVersion(Document):
	def validate(self):
		if not self.is_new() and not _bypass(frappe.session.user):
			frappe.throw(_("Whiteboard versions cannot be edited"))

	def on_trash(self):
		if not _bypass(frappe.session.user):
			frappe.throw(_("Whiteboard versions cannot be deleted"), frappe.PermissionError)
