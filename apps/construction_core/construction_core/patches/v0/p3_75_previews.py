"""P3-75 (design §15.3, §15.8): chat files sent before the previews row get theirs. Each sent attachment of a type a
reader takes, with no preview of its own (P3-65 made only photos'), becomes pending with a Preview Image row that the
five-minute sweep queues on the thumbs worker; any other type shows "not supported". Project files are not touched:
they get previews when first viewed (§15.9). Safe to re-run: rows already armed are skipped."""

import frappe

from construction_core.previews import jobs, store
from construction_core.previews.sources import Target


def execute():
	rows = frappe.get_all("Discuss Attachment", filters={"state": "Sent", "has_preview": 0, "file": ["is", "set"]},
		or_filters=[["preview_state", "is", "not set"], ["preview_state", "=", ""]],
		fields=["name", "file", "content_hash", "ext", "source"])
	for r in rows:
		if not jobs.previewable(r.ext) or not (r.content_hash or "").isalnum():
			frappe.db.set_value("Discuss Attachment", r.name, {"preview_state": "skipped",
				"preview_reason": "not_supported"}, update_modified=False)
			continue
		row = store.ensure(Target("File", r.file, r.content_hash, r.ext or "", scanned=r.source in ("Upload", "Copy")))
		if row and row.state in store.FINAL:
			store.sync_attachments(row, row.state, row.reason, row.width, row.height, row.info)
		else:
			frappe.db.set_value("Discuss Attachment", r.name, "preview_state", "pending", update_modified=False)
