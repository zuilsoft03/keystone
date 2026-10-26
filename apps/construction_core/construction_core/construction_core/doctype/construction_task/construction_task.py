# Copyright (c) 2026, Construction Workspace and contributors
"""Construction Task (P1-20, D-104): a task, optionally on a project (replaces ERPNext's Task). Start and end dates
give Frappe's Gantt view; a task with no project keeps Frappe's own permission (§2.1 pass-through)."""

from frappe.model.document import Document


class ConstructionTask(Document):
	pass
