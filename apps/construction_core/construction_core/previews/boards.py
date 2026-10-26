"""A Canvas board's preview (P3-75, design §15.2, §15.3): the editor's own picture, sent after a save.

The browser exports the board (PNG, at most 512 px) once a save succeeds and the board is idle, and posts it with the
version it shows. The server takes it only for the board's current version (an older tab never overwrites a newer
picture), checks the header (PNG, at most 1024 px a side, at most 2 MB) before any pixel is decoded, and draws it again
as a WebP of at most 400 px with no metadata. A board keeps one preview, its newest; after a restore (a save with no
browser) it shows the placeholder until the next save from the editor. A failed picture never fails the save.
"""

import base64
from io import BytesIO

import frappe
from frappe import _

from construction_core.previews import PX, store
from construction_core.previews.readers import common
from construction_core.previews.sources import Target

MAX_BYTES = 2 * 1024 * 1024
MAX_SIDE = 1024
PREFIX = "data:image/png;base64,"


def take(board: str, version: int, image: str) -> dict:
	"""Store the board's picture for ``version``. The caller has checked that the user edits the board."""
	current = frappe.db.get_value("Whiteboard", board, "version", for_update=True)  # a save waits for this picture
	if current is None or int(current) != int(version):
		frappe.throw(_("The board has a newer version; its picture is taken from that one."), frappe.ValidationError)
	png = _decoded(image)
	try:
		result = _drawn(png)
	except common.Refused:
		frappe.throw(_("This picture of the board could not be read."))
	target = Target("Whiteboard", board, f"v{int(version)}", "png", scanned=True, server=False)
	row = store.ensure(target)
	store.mark_ready(row, "board", result.width, result.height, result.webp, {})
	older = frappe.get_all("Preview Image", filters={"source_type": "Whiteboard", "source_name": board,
		"source_key": ["!=", target.key]}, pluck="name")
	if older:
		from construction_core.previews.purge import drop_unused

		paths = frappe.get_all("Preview Image", filters={"name": ["in", older]}, pluck="path")
		frappe.db.delete("Preview Image", {"name": ["in", older]})
		frappe.db.after_commit.add(lambda: drop_unused(paths))
	return {"version": int(version), "w": result.width, "h": result.height}


def _decoded(image) -> bytes:
	if not isinstance(image, str) or not image.startswith(PREFIX) or len(image) > len(PREFIX) + MAX_BYTES * 4 // 3 + 4:
		frappe.throw(_("Send the board's picture as a PNG of at most 2 MB."))
	try:
		png = base64.b64decode(image[len(PREFIX):], validate=True)
	except ValueError:
		frappe.throw(_("Send the board's picture as a PNG of at most 2 MB."))
	if len(png) > MAX_BYTES or not png.startswith(common.PNG_SIGNATURE):
		frappe.throw(_("Send the board's picture as a PNG of at most 2 MB."))
	return png


def _drawn(png: bytes):
	"""The header first (PNG, at most 1024 px a side), then one decode and the WebP."""
	image = common.open_capped(BytesIO(png), MAX_SIDE * MAX_SIDE, ("PNG",))
	if image.width > MAX_SIDE or image.height > MAX_SIDE:
		raise common.Refused(common.TOO_LARGE)
	try:
		image.load()
	except Exception:
		raise common.Refused(common.FAILED) from None
	return common.to_webp(image, PX)
