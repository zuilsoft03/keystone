# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Follow: who takes part in a thread and why (D-418, design §14.5), the source of thread unread and "Mentions
me". One row per (thread, user). Written only by discuss.rooms.write_follows, after the message's commit (never inside
the message transaction, F15, D-353): the authors, the people mentioned and the root message's author, and by
mark_read for the people who open the thread. Staff read it; clients never do."""

import frappe
from frappe.model.document import Document


class DiscussFollow(Document):
	pass


def on_doctype_update():
	frappe.db.add_unique("Discuss Follow", ["thread", "user"], constraint_name="unique_thread_user")
	# The inbox reads one user's follows across their rooms (design §14.6, P3-74).
	frappe.db.add_index("Discuss Follow", ["user", "thread"], "user_thread")
