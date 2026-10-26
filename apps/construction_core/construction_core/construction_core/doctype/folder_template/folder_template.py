# Copyright (c) 2026, Construction Workspace and contributors
"""Folder Template: the folder tree a new project gets (P1-05). Paths are relative to the project root."""

import frappe
from frappe import _
from frappe.model.document import Document


class FolderTemplate(Document):
	def validate(self):
		for row in self.folders:
			path = (row.path or "").strip()
			parts = path.split("/")
			if not path or path.startswith("/") or "\\" in path or any(p.strip() in ("", ".", "..") for p in parts):
				frappe.throw(_("Row {0}: a folder path is relative to the project, like 02_Design/Drawings").format(row.idx))
			row.path = "/".join(p.strip() for p in parts)
