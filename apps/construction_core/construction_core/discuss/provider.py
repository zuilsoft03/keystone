"""DiscussChat: the v1 ChatProvider, on our own Discuss Thread / Discuss Message (D-080)."""

import frappe

from construction_core.providers.chat import AUDIENCES, ChatProvider

# The words people see for our own doctypes (D-104): a thread on a Construction Project reads "Project PROJ-0010".
DISPLAY = {"Construction Project": "Project", "Construction Task": "Task", "Whiteboard": "Board",
	"Discuss Message": "Message"}
PAGE = 50  # the newest messages a thread read returns (F1, F2)


def label(anchor_doctype: str, anchor_name: str) -> str:
	"""A record's thread stores its type and number, never the record's title (F11): "Board WB-PROJ-0001-001". A File's
	name is an id that never leaves (SEC-4) and it has no number, so its thread is "File" (P3-66, "Discuss this")."""
	if anchor_doctype == "File":
		return "File"
	return f"{DISPLAY.get(anchor_doctype, anchor_doctype)} {anchor_name}"


class DiscussChat(ChatProvider):
	name = "discuss"

	def ensure_thread(self, anchor_doctype, anchor_name, audience="Internal", title=None):
		"""The record's open thread for ``audience``, made on first use. A project's is its room (D-418): what the
		callers mean by "the project's conversation". One on a message is got or made under a lock on the message.
		``title`` is kept for a project thread (its author's text); a record's thread takes its neutral label."""
		from construction_core.discuss import rooms

		if audience not in AUDIENCES:
			frappe.throw(f"Unknown audience {audience}")
		if anchor_doctype == "Construction Project":
			frappe.has_permission(anchor_doctype, "read", doc=anchor_name, throw=True)
			existing = rooms.room(anchor_name, audience)
		else:
			existing = rooms.open_thread(anchor_doctype, anchor_name, audience)
		if existing:
			frappe.get_doc("Discuss Thread", existing).check_permission("read")
			return existing
		return frappe.get_doc({"doctype": "Discuss Thread", "anchor_doctype": anchor_doctype, "anchor_name": anchor_name,
			"audience": audience, "title": title or label(anchor_doctype, anchor_name)}).insert().name

	def post(self, thread_id, text, file=None):
		"""The ChatProvider contract (D-080), on the one send path: a client goes through the portal checks."""
		from construction_core.discuss.send import send_impl

		return send_impl(thread_id, text, file=file)

	def messages(self, thread_id, user: str | None = None):
		"""The thread's newest PAGE messages as ``user`` reads them, oldest first (None: the session user, with today's
		errors). The server-rendered portal's read (FIT-10): it bypasses the response exit until P3-64 moves it."""
		from construction_core.discuss.read import visible_messages

		thread = frappe.get_doc("Discuss Thread", thread_id)
		if user is None:
			thread.check_permission("read")
		elif not frappe.has_permission("Discuss Thread", "read", doc=thread, user=user):
			raise frappe.PermissionError
		return list(reversed(visible_messages(user or frappe.session.user, thread_id, limit=PAGE)))
