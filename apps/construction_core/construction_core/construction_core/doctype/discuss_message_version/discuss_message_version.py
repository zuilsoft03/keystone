# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Message Version: a text a chat message had before an edit (P3-68, D-388, design §3.8), a ChatRow.

- An edit stores the text, mentions and tags it replaces here, then sets the message's row with db_set: every reader,
  Frappe's routes included, gets only the latest text, and the earlier texts stay as the record (SEC-1, FIT-02).
- Project staff read it (the history); clients never do. A removal moves these rows to Discuss Removed Text and
  deletes them here (D-388).
"""

from construction_core.discuss.rows import ChatRow


class DiscussMessageVersion(ChatRow):
	pass


def on_doctype_update():
	from frappe import db

	db.add_index("Discuss Message Version", ["message", "edited_on"], "message_edited_on")
