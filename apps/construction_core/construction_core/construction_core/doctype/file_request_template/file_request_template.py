# Copyright (c) 2026, Construction Workspace and contributors
"""File Request Template: a saved checklist (P3-71, design §3.10). Staff create and read; only a System Manager deletes.
No project: it is not scoped, and it names no person and no file."""

import json

from frappe.model.document import Document


class FileRequestTemplate(Document):
	def validate(self):
		from construction_core.discuss.parts.file_requests import template_items

		self.title = (self.title or "").strip()
		self.items = json.dumps(template_items(self.items))
