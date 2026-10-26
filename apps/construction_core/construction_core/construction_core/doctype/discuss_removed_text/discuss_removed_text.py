# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Removed Text: what a removed chat message said (P3-68, D-388, design §3.8), a ChatRow.

- A removal moves the message's text and mentions, every earlier text and its tags here, deletes them from their own
  doctypes, and empties the message row with db_set. The message then shows as removed.
- System Managers only: no staff member and no client reads a removed text (SEC-1, SEC-8).
"""

from construction_core.discuss.rows import ChatRow


class DiscussRemovedText(ChatRow):
	pass
