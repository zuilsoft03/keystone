# Copyright (c) 2026, Construction Workspace and contributors
"""Approval Settings (P3-77, approvals design §3.2 item 3): the site's evidence mailbox. Server-owned: it changes only
through construction_core.approvals.api (set_evidence_mailbox, confirm_evidence_mailbox), whose guard refuses any other
save, a System Manager's and Administrator's too."""

from frappe.model.document import Document


class ApprovalSettings(Document):
	pass
