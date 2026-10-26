# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Attachment: a file a chat message carries (P3-65, design §3.2), a ChatRow (discuss.rows).

- Made by ``discuss.media`` at upload (or Attach from Files) as a Pending row of its uploader, with its bytes staged
  outside the site's files: no File, no Files list, nothing a client or the team can list (SEC-4, FIT-11).
- Claimed by the send (``discuss.parts.attachments``): the same user, the same thread, pending and not expired, under
  a row lock; the send then makes the File in the conversation's folder and marks the row Sent.
- Read through Frappe by project staff (Construction Manager, Construction Staff), and then only Sent rows and their own
  waiting uploads (permissions.can_access and project_scoped); written by the server only (System Manager in Desk).
  Clients never read a row: what a viewer sees of a file is the message's card, drawn per viewer (rule 2, rule 4).
- Deleted only by the purge (D-389), the uploader's own discard, or a System Manager.
"""

from construction_core.discuss.rows import ChatRow


class DiscussAttachment(ChatRow):
	def on_chat_insert(self, claim):
		self.uploader = claim.fields["uploader"]
		self.state = "Pending"


def on_doctype_update():
	"""The send claims and the purge find pending rows by thread and uploader, or by their expiry."""
	from frappe import db

	db.add_index("Discuss Attachment", ["thread", "uploader", "state"], "thread_uploader_state")
	db.add_index("Discuss Attachment", ["state", "expires_on"], "state_expires_on")
