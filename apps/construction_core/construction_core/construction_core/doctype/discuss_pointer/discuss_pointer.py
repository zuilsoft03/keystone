# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Pointer: a reference from a chat message to what it points at (D-418, design §14.2), a part's data.

- Written only by the server (discuss.parts.pointer.add), and only when every reader of the message can read the
  target (§14.4 row 2). The target name is Data, never a Link, so Frappe's dotted selectors cannot join through it.
  Its targets: a thread, a message, a design record (P3-69) and an approval request (P3-78: the card in the Client
  room and the Team room's line, drawn by the approval part).
- Project, audience and staff_only are copied from the message, like every chat row. Staff read it; clients never do
  (their payloads carry what the part draws).
- A pointer is never changed or deleted, but by a System Manager: an edit or removal of its message reaches it through
  the message (P3-68).
"""

import frappe
from frappe import _
from frappe.model.document import Document

from construction_core.discuss.parts import pointer
from construction_core.permissions import _bypass


class DiscussPointer(Document):
	def before_insert(self):
		pointer.check(self)

	def validate(self):
		if not self.is_new() and not _bypass(frappe.session.user):
			frappe.throw(_("References cannot be changed"), frappe.PermissionError)

	def on_trash(self):
		if not _bypass(frappe.session.user):
			frappe.throw(_("References cannot be deleted"), frappe.PermissionError)


def on_doctype_update():
	"""P3-68 finds the mirrors of a reply by their target."""
	frappe.db.add_index("Discuss Pointer", ["target_type", "target_name"], "target_type_name")
