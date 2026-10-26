# Copyright (c) 2026, Construction Workspace and contributors
"""Approval Route Version (approvals design §14.2; P3-82): one saved route, append-only. Inserted only under
approvals.log's claim, with ``sha256`` = SHA-256 of its canonical text; never saved, renamed or deleted (LedgerRow)."""

from construction_core.approvals import canonical, log


class ApprovalRouteVersion(log.LedgerRow):
	def check_insert(self):
		if canonical.sha256(self.canonical or "") != self.sha256:
			log.refuse()
