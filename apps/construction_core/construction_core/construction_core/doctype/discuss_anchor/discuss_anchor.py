# Copyright (c) 2026, Construction Workspace and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DiscussAnchor(Document):
	pass


def on_doctype_update():
	"""A thread finds its anchor row, and a message the thread it is the root of (P3-73)."""
	frappe.db.add_index("Discuss Anchor", ["thread_id"], "thread_id_index")
	frappe.db.add_index("Discuss Anchor", ["message_id"], "message_id_index")
