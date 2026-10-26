# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Poll Vote: one person's vote for one option (P3-68, design §3.7), a ChatRow (discuss.rows).

- One row per person and option; a one-choice poll stores the slot 'single', so unique (poll, user, slot) is also the
  one-vote rule of a one-choice poll. The vote is stored with its voter even in an anonymous poll, for that rule.
- System Manager only (SEC-3): an anonymous poll names no voter to anyone else. Made and removed by the polls part.
"""

from construction_core.discuss.rows import ChatRow


class DiscussPollVote(ChatRow):
	pass


def on_doctype_update():
	from frappe import db

	db.add_unique("Discuss Poll Vote", ["poll", "user", "slot"], constraint_name="unique_poll_user_slot")
	db.add_index("Discuss Poll Vote", ["user", "poll"], "user_poll")
