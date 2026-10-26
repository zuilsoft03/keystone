# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Read State: how far one user has read one thread (seen receipts, D-098; unread counts). Written by
``discuss.api.mark_read`` only; staff read it, clients never do. One row per (thread, user) (F7)."""

import frappe
from frappe.model.document import Document


class DiscussReadState(Document):
	pass


def on_doctype_update():
	# Existing sites merge their duplicate rows first (patches.v0.p3_63_read_state_unique, before the model sync).
	frappe.db.add_unique("Discuss Read State", ["thread", "user"], constraint_name="unique_thread_user")
	# The inbox reads one user's read states across their rooms and threads (design §14.6, P3-74).
	frappe.db.add_index("Discuss Read State", ["user", "thread"], "user_thread")
