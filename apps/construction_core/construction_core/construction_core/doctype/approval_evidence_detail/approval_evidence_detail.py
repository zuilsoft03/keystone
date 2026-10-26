# Copyright (c) 2026, Construction Workspace and contributors
"""Approval Evidence Detail (approvals design §4.1, §4.8; D-428): an answer's personal values, kept beside the chain.

Inserted only under approvals.log's claim, with its event; never saved or renamed (LedgerRow). Deleted only by
log.clear_detail, under its own retention claim for this row, consumed once; saved only by log.clear_location, which
empties the location and nothing else (P3-81's retention job calls both).
"""

import frappe

from construction_core.approvals import log


class ApprovalEvidenceDetail(log.LedgerRow):
	no_feed_on_delete = True  # delete_doc's "Deleted" Comment: refused on a ledger row (log.refuse_ledger_reference)

	def check_save(self):
		before = self.get_doc_before_save()
		changed = [f for f in log.DETAIL_FIELDS + ("event", "project", "salt") if before and before.get(f) != self.get(f)]
		if frappe.flags.get(log.LOCATION) != self.name or not before or changed != ["location"] or self.location:
			log.refuse()

	def on_trash(self):
		claim = frappe.flags.get(log.RETENTION)
		if not claim or claim.consumed or claim.name != self.name:
			log.refuse()
		claim.consumed = True

	def after_delete(self):
		claim = frappe.flags.get(log.RETENTION)
		if not (claim and claim.consumed and claim.name == self.name):
			log.refuse()  # delete_doc skipped on_trash (ignore_on_trash)
