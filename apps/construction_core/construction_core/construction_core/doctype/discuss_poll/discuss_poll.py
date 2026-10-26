# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Poll: the poll a chat message carries (P3-68, design §3.7), a ChatRow (discuss.rows).

- Made only by the polls part's write, under the send's claim, after the message insert: never by REST or Desk.
- Its options are JSON on the row (key, text and an optional picture: an attachment of the same message), and so are
  its tallies (``tally``, and ``voters`` for a named poll), recounted from the vote rows after each commit, so a card
  costs no query of its own (the lead's query budget).
- Read by the server only (System Manager in Desk): viewers see the card the part draws for them.
"""

from construction_core.discuss.rows import ChatRow


class DiscussPoll(ChatRow):
	pass


def on_doctype_update():
	"""One poll per message; a page reads its polls by message."""
	from frappe import db

	db.add_unique("Discuss Poll", ["message"], constraint_name="unique_poll_message")
