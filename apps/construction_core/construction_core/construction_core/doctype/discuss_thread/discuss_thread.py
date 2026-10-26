# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Thread: a conversation anchored to one record, with an audience (D-080, D-086, DR-9).

- The thread belongs to its record's project, and its creator must be able to read the record.
- A Client thread may be anchored only to a record that clients may see; Internal threads are never visible to
  clients. Each thread gets a provider-neutral ``Discuss Anchor`` row (ARCHITECTURE §6.8).
- A record's thread stores a neutral label, the record's type and number, whatever the caller sent (F11, D-370):
  clients read thread rows through Frappe's own routes, and a record's title must not outlive its unshare. A project
  thread keeps its author's text.
- Rooms and threads (D-418, discuss.rooms): a room is the server's own row, keyed ``<project>|<audience>``; every
  other thread is put in its room before its insert, and gets its root (the message it was opened on, or a root card
  in its room) after it. ``room_key`` and ``in_room`` are set once; a room keeps its title and status.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from construction_core.discuss import rooms
from construction_core.discuss.provider import label
from construction_core.permissions import client_may_see, is_client, project_of


class DiscussThread(Document):
	def before_insert(self):
		rooms.place(self)

	def validate(self):
		anchor = frappe.get_doc(self.anchor_doctype, self.anchor_name)
		project = anchor.name if anchor.doctype == "Construction Project" else project_of(anchor)
		if not project:
			frappe.throw(_("A thread must be anchored to a project record"))
		if self.project and self.project != project:
			frappe.throw(_("The thread's project must be the record's project"))
		self.project = project
		if self.anchor_doctype != "Construction Project":
			self.title = label(self.anchor_doctype, self.anchor_name)
		if self.is_new() and not self.room_key:  # a room is the server's, made for whoever first needs it
			anchor.check_permission("read")
			if is_client(frappe.session.user) and not rooms.opener_allowed(self):  # QR-2: the portal endpoint only
				frappe.throw(_("Clients post in existing threads; staff open them"), frappe.PermissionError)
		if self.audience == "Client" and anchor.doctype != "Construction Project" and not client_may_see(anchor):
			frappe.throw(_("A client thread needs a record that clients can see (mark it client visible first)"))
		before = self.get_doc_before_save()
		if before and before.audience != self.audience:
			frappe.throw(_("A thread's audience cannot change: open a new thread instead"))
		rooms.check(self, anchor)

	def before_rename(self, old, new, merge=False):
		"""A room, and a thread a pointer or an anchor names, keep their name: those name it as Data (D-418), which a
		rename would leave behind. Every thread has its anchor row, so in practice no chat thread is renamed."""
		if self.room_key or (frappe.db.exists("Discuss Pointer", {"target_type": "Discuss Thread", "target_name": old})
				or frappe.db.exists("Discuss Anchor", {"thread_id": old})):
			frappe.throw(_("A conversation keeps its name"), frappe.PermissionError)

	def after_insert(self):
		# ignore_permissions: the anchor row is the system's index of threads, not a user record.
		anchor = frappe.get_doc({
			"doctype": "Discuss Anchor", "project": self.project, "anchor_doctype": self.anchor_doctype,
			"anchor_name": self.anchor_name, "provider": "discuss", "thread_id": self.name,
			"audience": self.audience, "created_by": frappe.session.user,
		}).insert(ignore_permissions=True)
		rooms.root(self, anchor.name)


def on_doctype_update():
	"""A record's threads are found by their anchor and audience; the locking read of a message's thread
	(rooms.open_thread) then locks only that message's threads of that audience, so a busy thread of the other audience
	cannot make it meet 1020, and never scans every thread row."""
	frappe.db.add_index("Discuss Thread", ["anchor_doctype", "anchor_name", "audience"], "anchor_doctype_name_audience")
