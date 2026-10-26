"""Preview Image rows and the stored WebPs (P3-75, design §15.3).

The bytes live under ``<site>/private/thumbs/`` (outside private/files: never a File, never in Files, the bin or
search, and ``bench backup`` skips them, D-421). A stored preview is named by the sha256 of the source's bytes, the
spec and the renderer version; the job reads the bytes, so the sha256 is always its own. Frappe's ``content_hash`` (MD5)
only finds a row and is checked against the bytes; it never decides that two sources share a preview or a scan. A
board's preview is named by the board and its version.

Each source has its own row; a chat card takes the answer of the row of its own file (``sync_attachments``). What a
viewer may see is decided at every read (``api``), never by a row. Removal is ``purge``.
"""

import hashlib
import json
import os

import frappe
from frappe.utils import add_to_date, get_datetime, get_site_path, now_datetime

from construction_core.previews import DOCTYPE, RENDERER_VERSION, SPEC

THUMBS = "thumbs"
ROW_FIELDS = ["name", "source_type", "source_name", "source_key", "sha256", "ext", "state", "reason", "path", "width",
	"height", "info", "renderer_version", "scanned", "attempts", "retry_after"]
FINAL = ("ready", "failed", "skipped")
BACKOFF = (60, 300, 1800, 7200, 43200)  # seconds before each retry of a passing failure; then it stops (G6)
REST = 86400  # a preview that stopped on "service down" may be asked for again after a day


def stored_path(name: str | None) -> str | None:
	"""A stored preview's path, only ever a bare name inside the thumbs folder."""
	if not name or os.path.basename(name) != name or name.startswith(".") or not name.endswith(".webp"):
		return None
	return get_site_path("private", THUMBS, name)


def file_name(row) -> str:
	"""A File's preview by the sha256 of its bytes; a board's by its name and version, so two boards never share."""
	key = row.sha256 if row.source_type == "File" and row.sha256 else hashlib.sha256(
		f"{row.source_type}:{row.source_name}:{row.source_key}".encode()).hexdigest()
	return f"{key}-{SPEC}-{RENDERER_VERSION}.webp"


def row_of(target) -> frappe._dict | None:
	return frappe.db.get_value(DOCTYPE, {"source_type": target.source_type, "source_name": target.source_name,
		"source_key": target.key, "spec": SPEC}, ROW_FIELDS, as_dict=True)


def wants_work(row) -> bool:
	"""Whether a row needs the job: none yet, an older renderer's, a retry that is due, or a stop that has rested."""
	if not row:
		return True
	if row.renderer_version != RENDERER_VERSION:
		return True
	if row.state == "ready" and not os.path.exists(stored_path(row.path) or ""):
		return True  # its stored preview was lost (previews are not backed up): made again
	due = not row.retry_after or get_datetime(row.retry_after) <= now_datetime()
	return due and (row.state == "pending" or (row.state == "failed" and row.reason == "service_down"))


def ensure(target) -> frappe._dict:
	"""The target's row, made pending when missing. Nothing is copied here: only the job, which has the bytes, may
	reuse another row's answer."""
	row = row_of(target)
	if row:
		return row
	try:
		frappe.get_doc({"doctype": DOCTYPE, "source_type": target.source_type, "source_name": target.source_name,
			"source_key": target.key, "spec": SPEC, "renderer_version": RENDERER_VERSION, "ext": target.ext,
			"state": "pending", "scanned": 1 if target.scanned else 0}).insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		frappe.clear_last_message()  # a job made it meanwhile
	return row_of(target)


def twin_values(sha256: str) -> dict:
	"""A final row of the same bytes (by sha256), spec and renderer version, as values to copy."""
	twin = frappe.db.get_value(DOCTYPE, {"sha256": sha256, "spec": SPEC, "renderer_version": RENDERER_VERSION,
		"state": ["in", FINAL], "reason": ["!=", "service_down"]}, ["state", "reason", "path", "width", "height", "info",
		"kind"], as_dict=True) if sha256 else None
	if not twin or (twin.state == "ready" and not os.path.exists(stored_path(twin.path) or "")):
		return {}
	return dict(twin)


def scanned_before(sha256: str) -> bool:
	return bool(sha256) and bool(frappe.db.exists(DOCTYPE, {"sha256": sha256, "scanned": 1}))


def mark_scanned(sha256: str) -> None:
	frappe.db.set_value(DOCTYPE, {"sha256": sha256}, "scanned", 1, update_modified=False)


def mark_ready(row, kind: str, width: int, height: int, webp: bytes, meta: dict) -> None:
	from construction_core.previews.purge import drop_unused
	from construction_core.providers.storage import write_atomic

	name = file_name(row)
	path = stored_path(name)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	write_atomic(path, webp)
	frappe.db.after_rollback.add(lambda: drop_unused([name]))  # a job that rolls back leaves no file behind
	finish(row, state="ready", reason=None, kind=kind, path=name, width=width, height=height, size=len(webp),
		info=json.dumps(meta) if meta else None)


def mark_final(row, state: str, reason: str, kind: str | None = None, meta: dict | None = None) -> None:
	finish(row, state=state, reason=reason, kind=kind, path=None, width=0, height=0, size=0,
		info=json.dumps(meta) if meta else None)


def mark_retry(row) -> None:
	"""A passing failure: try again after the next backoff step; after the last one, stop on "service down" (no
	endless retries, G6) until the preview is asked for again a day later."""
	attempts = int(row.attempts or 0) + 1
	if attempts > len(BACKOFF):
		finish(row, state="failed", reason="service_down", path=None, width=0, height=0, size=0, info=None,
			attempts=0, retry_after=add_to_date(now_datetime(), seconds=REST))
		return
	frappe.db.set_value(DOCTYPE, row.name, {"state": "pending", "attempts": attempts, "renderer_version": RENDERER_VERSION,
		"retry_after": add_to_date(now_datetime(), seconds=BACKOFF[attempts - 1])}, update_modified=False)
	sync_attachments(row, "pending", None)


def finish(row, **values) -> None:
	"""A row's answer, then the chat cards of its file take it, and their readers hear that the card changed."""
	from construction_core.previews.purge import drop_unused

	old = row.path
	values.setdefault("attempts", 0)
	values.setdefault("retry_after", None)
	values["renderer_version"] = RENDERER_VERSION
	frappe.db.set_value(DOCTYPE, row.name, {k: v for k, v in values.items() if k != "kind" or v}, update_modified=False)
	if sync_attachments(row, values["state"], values.get("reason"), values.get("width"), values.get("height"),
			values.get("info")):
		announce(row)
	if old and old != values.get("path"):
		frappe.db.after_commit.add(lambda: drop_unused([old]))


def sync_attachments(row, state: str, reason: str | None, width=None, height=None, meta=None) -> list:
	"""The sent chat cards of this row's own file and bytes show its answer from their own rows (no query of their
	own when cards are read). Photos whose preview came from their own decode (P3-65) are left as they are. Returns
	the attachments changed."""
	if row.source_type != "File":
		return []
	main = frappe.db.get_value("File", row.source_name, "cc_version_of") or row.source_name  # a revision's own file
	found = frappe.get_all("Discuss Attachment", filters={"file": main, "content_hash": row.source_key, "state": "Sent"},
		or_filters=[["has_preview", "=", 0], ["preview_state", "is", "set"]], pluck="name")
	if found:
		ready = state == "ready"
		frappe.db.set_value("Discuss Attachment", {"name": ["in", found]}, {"preview_state": state,
			"preview_reason": reason, "preview_meta": meta, "has_preview": 1 if ready else 0,
			"preview_w": (width or 0) if ready else 0, "preview_h": (height or 0) if ready else 0}, update_modified=False)
	return found


def announce(row) -> None:
	"""The chat's live router tells each message's own readers that its attachments part changed (ids only, after the
	commit); the screen reads the card again, through the reader's own rules."""
	from construction_core.discuss import live

	main = frappe.db.get_value("File", row.source_name, "cc_version_of") or row.source_name
	messages = frappe.get_all("Discuss Attachment", filters={"file": main, "content_hash": row.source_key,
		"state": "Sent", "message": ["is", "set"]}, pluck="message", distinct=True, limit=200)
	for m in frappe.get_all("Discuss Message", filters={"name": ["in", messages]}, fields=["name", "thread", "project",
			"audience", "staff_only"]) if messages else []:
		live.message_changed(m, part="attachments")
