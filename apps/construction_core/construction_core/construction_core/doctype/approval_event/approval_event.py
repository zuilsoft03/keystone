# Copyright (c) 2026, Construction Workspace and contributors
"""Approval Event (approvals design §4.1, §4.4; D-428): one link of a project's chain, append-only.

Inserted only under approvals.log's claim, with ``hash`` = SHA-256(prev_hash + "\\n" + canonical); never saved, renamed
or deleted, by anyone (LedgerRow). No role has permissions on it: the server reads it.
"""

import frappe

from construction_core.approvals import canonical, log


class ApprovalEvent(log.LedgerRow):
	def check_insert(self):
		try:
			linked = canonical.link(self.prev_hash, self.canonical) == self.hash
		except ValueError:
			linked = False
		if not linked:
			log.refuse()


def on_doctype_update():
	"""One event per place in a project's chain: two appends can never share a sequence number."""
	frappe.db.add_unique("Approval Event", ["project", "seq"], constraint_name="unique_project_seq")
