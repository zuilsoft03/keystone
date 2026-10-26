# Copyright (c) 2026, Construction Workspace and contributors
"""File Request Item: one file a request asks for (P3-71). Waiting, then Received (an upload is held), then Accepted.
Its rows change only through the part's endpoints (permissions.CHILD_DOCTYPES)."""

from frappe.model.document import Document


class FileRequestItem(Document):
	pass
