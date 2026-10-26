# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Reaction: one person's reaction to a chat message (P3-68, design §3.8), a ChatRow (discuss.rows).

- One row per (message, user, reaction), made and removed by the reactions part's endpoint only.
- System Manager only: viewers see the message's summary (``reactions``), recounted from these rows after each commit.
"""

from construction_core.discuss.rows import ChatRow


class DiscussReaction(ChatRow):
	pass


def on_doctype_update():
	from frappe import db

	db.add_unique("Discuss Reaction", ["message", "user", "reaction"], constraint_name="unique_message_user_reaction")
