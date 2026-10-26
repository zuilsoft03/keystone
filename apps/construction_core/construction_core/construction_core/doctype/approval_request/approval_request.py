# Copyright (c) 2026, Construction Workspace and contributors
"""Approval Request (approvals design §4.4, §7; D-428): a request and its frozen terms, written only by approvals.log.

- Insert only under log's claim, and only with ``terms_hash`` = SHA-256 of the snapshot and the shown copies as the
  snapshot lists them, starting Draft, Open or In internal review (P3-82).
- Save only under log's claim, changing nothing but the status, which must be the chain's (log.state_of), and the
  successor. Never renamed or deleted, by anyone (LedgerRow).
"""

import json

import frappe
from frappe.model import no_value_fields

from construction_core.approvals import canonical, log, read

MUTABLE = ("status", "successor")


class ApprovalRequest(log.LedgerRow):
	def check_insert(self):
		try:
			frozen = json.loads(self.snapshot)["frozen"] == json.loads(self.frozen_files)
		except (TypeError, ValueError, KeyError):
			frozen = False
		if not frozen or canonical.sha256(self.snapshot) != self.terms_hash \
				or self.status not in ("Draft", "Open", log.INTERNAL):
			log.refuse()

	def apply_fieldlevel_read_permissions(self):
		"""frappe.client.get, the desk form: the chain's neighbours only when the reader reads them too (a client never
		learns the id of a request in internal review). shortcut: get_list with these fields still returns them."""
		super().apply_fieldlevel_read_permissions()
		for field in ("predecessor", "successor"):
			if self.get(field) and frappe.session.user != "Administrator" and not read.readable(self.get(field)):
				self.set(field, None)

	def check_save(self):
		before = self.get_doc_before_save()
		if not before or self.status != log.state_of(self.name) or any(self.get(df.fieldname) != before.get(df.fieldname)
				for df in self.meta.fields if df.fieldtype not in no_value_fields and df.fieldname not in MUTABLE):
			log.refuse()


def on_doctype_update():
	"""A subject's requests (the rename guard, P3-77's gate) by record."""
	frappe.db.add_index("Approval Request", ["subject_doctype", "subject_name"], "subject_doctype_name")
