# Copyright (c) 2026, Construction Workspace and contributors
"""File Request: the files the team asks for in a conversation (P3-71, design §3.10), a ChatRow (discuss.rows).

- Made only by the file requests part's write, under the send's claim, after the card's message insert: never by REST
  or Desk, a System Manager's REST insert included. Its project, audience and staff_only are the message's.
- Changed only by the part's endpoints, with db.set_value on the row and its items and recipients (ChatRow refuses a
  save but for a System Manager).
- Read through Frappe by project staff (Construction Manager, Construction Staff); clients read it only through the
  card and the request page the part draws for them (not in CLIENT_READABLE).
"""

from construction_core.discuss.rows import ChatRow


class FileRequest(ChatRow):
	def on_chat_insert(self, claim):
		self.requested_by = claim.fields["requested_by"]
		self.status = "Open"


def on_doctype_update():
	"""One request per card; the daily reminders read open requests by their due date."""
	from frappe import db

	db.add_unique("File Request", ["message"], constraint_name="unique_file_request_message")
	db.add_index("File Request", ["status", "due_on"], "status_due_on")
