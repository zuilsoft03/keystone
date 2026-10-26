# Copyright (c) 2026, Construction Workspace and contributors
"""File Request Recipient: one person a request asks (P3-71), with the reminders they were sent (D-379, D-384). Its rows
change only through the part (permissions.CHILD_DOCTYPES)."""

from frappe.model.document import Document


class FileRequestRecipient(Document):
	pass
