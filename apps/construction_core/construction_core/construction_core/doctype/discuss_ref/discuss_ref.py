# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Ref: a file or record a chat message tags with ``#[r:n]`` (P3-66, design §3.5), a ChatRow (discuss.rows).

- Made only by the refs part's write, under the send's claim, after the message insert: never by REST or Desk, a
  System Manager's insert included (the ChatRow claim).
- ``ref_doctype`` and ``ref_name`` are Data, never a Link (D-418): Frappe's dotted selectors cannot join through them,
  and the record can still be deleted; a ref to a deleted record draws no card.
- Read by the server only (System Manager in Desk): staff and clients see the message's card, drawn per viewer by
  records.resolve, never the row (P3-66 audit C2).
- The insert checks once more that the type is registered for the message's audience and that every reader of the
  message may read the record (§14.4 row 2); the send's claim checked it as the sender first.
"""

from construction_core.discuss.rows import ChatRow


class DiscussRef(ChatRow):
	def on_chat_insert(self, claim):
		from construction_core.discuss.parts import refs

		refs.check_row(self)


def on_doctype_update():
	"""A page's cards read its messages' refs in one query."""
	from frappe import db

	db.add_index("Discuss Ref", ["message", "position"], "message_position")
