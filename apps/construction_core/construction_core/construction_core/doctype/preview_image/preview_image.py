# Copyright (c) 2026, Construction Workspace and contributors
"""Preview Image (P3-75, design §15.3): one source's preview of one key (a content hash, or a board version), with
its state and reason. Rows with the same key, spec and renderer version share one stored WebP. System Manager only;
viewers reach previews through construction_core.previews.api, by the source's own rule."""

from frappe.model.document import Document


class PreviewImage(Document):
	pass


def on_doctype_update():
	"""One row per source and key; the job finds a ready or failed twin by key, the sweep finds due rows by state."""
	from frappe import db

	db.add_unique("Preview Image", ["source_type", "source_name", "source_key", "spec"], "source_key_spec")
	db.add_index("Preview Image", ["sha256", "spec", "renderer_version"], "sha_spec_version")
	db.add_index("Preview Image", ["state", "retry_after"], "state_retry_after")
