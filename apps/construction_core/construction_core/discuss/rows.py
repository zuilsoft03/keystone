"""The ChatRow base (design §13.3, §13.6 step 5): a chat doctype whose rows only the server writes (P3-65).

A chat row belongs to one thread and, once sent, one message. Its project, thread, audience and staff_only are copied
from the message (or, before the send, from the thread) by the server, never taken from the caller (rule 4). Rules:

- **Insert** only under ``insert()``'s claim, bound to (doctype, thread, message) and consumed once. Any other insert is
  refused, a System Manager's REST insert too: the claim is a request-local flag no payload reaches.
- **Change** is the server's ``db.set_value`` under the part's write (the send's claim); a save through Frappe is
  refused but for a System Manager.
- **Delete** only by a System Manager (Desk) or the server's own purge, which removes rows with ``db.delete``.

A subclass implements ``on_chat_insert(claim)`` only: what it checks or sets from the claim's ``fields``.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from construction_core.permissions import _bypass

CLAIM = "cc_chat_row"


class ChatRow(Document):
	def before_insert(self):
		claim = frappe.flags.get(CLAIM)
		if (not claim or claim.consumed or claim.doctype != self.doctype or claim.thread != self.thread
				or (claim.message or None) != (self.get("message") or None)):
			frappe.throw(_("Chat rows are made by the server"), frappe.PermissionError)
		claim.consumed = True
		columns(self, claim.thread, claim.message)
		self.on_chat_insert(claim)

	def on_chat_insert(self, claim) -> None:
		"""What the subclass checks or sets from ``claim.fields`` (the server's own values)."""

	def validate(self):
		if not self.is_new() and not _bypass(frappe.session.user):
			frappe.throw(_("Chat rows are changed by the server"), frappe.PermissionError)

	def on_trash(self):
		if not _bypass(frappe.session.user):
			frappe.throw(_("Chat rows are removed by the server"), frappe.PermissionError)


def columns(doc, thread: str, message: str | None) -> None:
	"""The chat columns, from the message when there is one, else from the thread (a staged upload)."""
	if message:
		m = frappe.db.get_value("Discuss Message", message, ["thread", "project", "audience", "staff_only"],
			as_dict=True)
		if not m or m.thread != thread:
			frappe.throw(_("Chat rows are made by the server"), frappe.PermissionError)
		doc.project, doc.audience, doc.staff_only = m.project, m.audience, m.staff_only
	else:
		t = frappe.db.get_value("Discuss Thread", thread, ["project", "audience"], as_dict=True)
		if not t:
			frappe.throw(_("Chat rows are made by the server"), frappe.PermissionError)
		doc.project, doc.audience, doc.staff_only = t.project, t.audience, 0


def insert(doctype: str, values: dict, thread: str, message: str | None = None) -> str:
	"""The one way a chat row is made: as the server, under a claim for exactly this row."""
	frappe.flags[CLAIM] = frappe._dict(doctype=doctype, thread=thread, message=message, fields=values,
		consumed=False)
	try:
		# ignore_permissions: the server's row (rule 4); before_insert still checks the claim.
		return frappe.get_doc({"doctype": doctype, **values, "thread": thread, "message": message}).insert(
			ignore_permissions=True).name
	finally:
		frappe.flags[CLAIM] = None
