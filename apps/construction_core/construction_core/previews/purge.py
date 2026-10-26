"""Removing previews (P3-75, design §15.3).

Delete, unshare and the bin remove a file's rows; a permanent delete (or the bin's purge) also clears the preview of
every chat card of that file, so P3-65's photo previews of deleted files no longer stay behind. A stored file is
deleted only when no row uses it any more: no Preview Image row, and no chat photo whose preview came from its own
decode (P3-65's ``<hash>-p400.webp``). Whoever still reads the file sees its preview made again on the next view.
"""

import os
import time

import frappe
from frappe.utils import get_site_path

from construction_core.previews import DOCTYPE
from construction_core.previews.store import THUMBS, stored_path


def remove_rows(source_type: str, names: list) -> None:
	"""A source's rows go, then (after the commit) any stored file no row uses."""
	if not names:
		return
	rows = frappe.get_all(DOCTYPE, filters={"source_type": source_type, "source_name": ["in", names]},
		fields=["name", "path"])
	if not rows:
		return
	frappe.db.delete(DOCTYPE, {"name": ["in", [r.name for r in rows]]})
	paths = [r.path for r in rows if r.path]
	frappe.db.after_commit.add(lambda: drop_unused(paths))


def drop_unused(names) -> int:
	"""Delete the stored previews in ``names`` that no Preview Image row and no chat photo uses. Returns how many."""
	from construction_core.discuss import media

	gone = 0
	for name in dict.fromkeys(n for n in names if n):
		path = stored_path(name)
		if not path or not os.path.exists(path) or frappe.db.exists(DOCTYPE, {"path": name}):
			continue
		digest = name.split("-", 1)[0]
		if name == os.path.basename(media.preview_path(digest) or "") and frappe.db.exists("Discuss Attachment",
				{"content_hash": digest, "has_preview": 1}):
			continue
		os.remove(path)
		gone += 1
	return gone


def on_file_trash(doc, method=None) -> None:
	"""File on_trash (a permanent delete, or the bin's purge): its rows and its versions' rows go, and the chat cards of
	those files lose their previews (the card is not shown without its file), then the stored files no row uses."""
	if doc.is_folder:
		return
	names = [doc.name, *frappe.get_all("File", filters={"cc_version_of": doc.name}, pluck="name")]
	remove_rows("File", names)
	hashes = frappe.get_all("Discuss Attachment", filters={"file": doc.name, "has_preview": 1}, pluck="content_hash")
	frappe.db.set_value("Discuss Attachment", {"file": doc.name}, {"has_preview": 0, "preview_state": "",
		"preview_reason": None, "preview_w": 0, "preview_h": 0}, update_modified=False)
	from construction_core.discuss import media

	legacy = [os.path.basename(p) for p in (media.preview_path(h) for h in set(hashes)) if p]
	frappe.db.after_commit.add(lambda: drop_unused(legacy))


def sweep(batch: int = 2000) -> int:
	"""Hourly: chat cards whose file is gone lose their previews (P3-65 left those behind), and stored previews no row
	uses any more are deleted (a job that died between its write and its commit). A file younger than an hour is left
	alone: its job may still be running."""
	table = frappe.qb.DocType("Discuss Attachment")
	files = frappe.qb.DocType("File")
	orphans = (frappe.qb.from_(table).left_join(files).on(files.name == table.file).select(table.name)
		.where(table.has_preview == 1).where(table.file.isnotnull()).where(files.name.isnull()).limit(batch)).run(pluck=True)
	if orphans:
		frappe.db.set_value("Discuss Attachment", {"name": ["in", orphans]}, {"has_preview": 0, "preview_state": "",
			"preview_w": 0, "preview_h": 0}, update_modified=False)
	folder = get_site_path("private", THUMBS)
	if not os.path.isdir(folder):
		return 0
	cutoff = time.time() - 3600
	old = [e.name for e in os.scandir(folder) if e.is_file() and e.name.endswith(".webp") and e.stat().st_mtime < cutoff]
	return drop_unused(old[:batch])


def on_board_trash(doc, method=None) -> None:
	"""Whiteboard on_trash: its picture's row goes, then its stored file."""
	remove_rows("Whiteboard", [doc.name])


def on_file_event(event: str, doctype: str, doc_name: str) -> None:
	"""cc_event_handlers (after the commit, on the short queue): a file put in the bin, or no longer shared with the
	client, loses its rows (§15.3)."""
	if doctype != "File" or not frappe.db.exists("File", doc_name):
		return
	if event == "storage.visibility_changed" and frappe.db.get_value("File", doc_name, "cc_client_visible"):
		return  # shared: nothing to remove
	remove_rows("File", [doc_name])
