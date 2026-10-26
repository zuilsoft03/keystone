# Copyright (c) 2026, Construction Workspace and contributors
"""Backup Settings (P2-01, D-103, D-107): the off-host copy of the nightly backup sets, set by a System Manager.

Where the copies go (the NAS share) is the server's settings file (OFFSITE_DIR); how long they are kept there is
here. The backup service records the last copy's result in the read-only fields (construction_core.backups)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class BackupSettings(Document):
	def validate(self):
		if cint(self.offsite_keep_days) < 1:
			frappe.throw(_("Keep copies for at least 1 day"))
