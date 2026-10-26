"""The one preview endpoint (P3-75, design §15.3; SEC-8, Q-105).

``image`` serves a source's preview to a viewer the source's own rule lets in (``sources``): ``?kind=`` one registered
kind (attachment, file, board) and ``&name=`` its id, so a new kind adds no parameter. Missing, unreadable, not ready
and unknown are one "not found". The answer is ``image/webp`` with ``nosniff`` and ``no-store``, read from the thumbs
folder here, never through send_private_file (its long private cache is Q-105's problem). A preview not made yet is
asked for (existing files get previews when first viewed, §15.9), without a write in the read.

``states`` answers a list of sources at once (the Files list), and asks for the missing ones.
"""

import json
import os

import frappe
from werkzeug.wrappers import Response

from construction_core.previews import jobs, sources, store

MAX_STATES = 100


@frappe.whitelist(methods=["GET"])
def image(kind: str, name: str):
	"""``kind``: a registered source kind; ``name``: that source's id (an attachment id, never a File id for a chat)."""
	return serve(kind, name)


def serve(kind: str, ident) -> Response:
	"""The preview of one source, or DoesNotExistError. P3-65's attachment preview link ends here too."""
	target = sources.resolve(kind, ident, frappe.session.user)
	if not target:
		raise frappe.DoesNotExistError
	path = _servable(target)
	if not path:
		raise frappe.DoesNotExistError
	with open(path, "rb") as fh:
		content = fh.read()
	return Response(content, status=200, content_type="image/webp", headers={"Cache-Control": "no-store",
		"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline", "Cross-Origin-Resource-Policy": "same-origin"})


@frappe.whitelist(methods=["POST"])
def states(kind: str, ids) -> dict:
	"""{id: {state, reason, w, h, meta}} for the ids the viewer may see; the others are left out. A missing or stale
	preview is asked for, and answers "pending"."""
	ids = frappe.parse_json(ids) if isinstance(ids, str) else ids
	if kind not in sources.SOURCES or not isinstance(ids, list) or len(ids) > MAX_STATES:
		frappe.throw(frappe._("Choose up to {0} items").format(MAX_STATES))
	out = {}
	for ident in dict.fromkeys(i for i in ids if isinstance(i, str)):
		target = sources.resolve(kind, ident, frappe.session.user)
		if target:
			out[ident] = _state(target)
	return out


def _servable(target) -> str | None:
	"""The stored preview of ``target``: a chat photo's own (made again from its bytes after a restore), else a ready
	row's. When there is none and work is due, the job is asked for."""
	from construction_core.discuss import media

	if target.legacy:
		if os.path.exists(target.legacy):
			return target.legacy
		if target.source_type == "File" and media.rebuild_preview(target.source_name, target.key, target.ext):
			return target.legacy
	row = store.row_of(target)
	path = store.stored_path(row.path) if row and row.state == "ready" else None
	if store.wants_work(row) or (row and row.state == "ready" and not (path and os.path.exists(path))):
		jobs.ask(target)  # missing, stale or lost (previews are not backed up): made again
	return path if path and os.path.exists(path) else None


def _state(target) -> dict:
	if target.legacy and os.path.exists(target.legacy):
		return {"state": "ready", "reason": None, "w": None, "h": None, "meta": {}}
	row = store.row_of(target)
	if store.wants_work(row):
		jobs.request(target)
		row = store.row_of(target)
	if not row and not target.server:  # a board's picture comes only from the editor's save: none until then
		return {"state": "none", "reason": None, "w": None, "h": None, "meta": {}}
	state = row.state if row else "pending"
	if state == "ready" and not os.path.exists(store.stored_path(row.path) or ""):
		state = "pending"  # its stored preview is being made again
	meta = json.loads(row.info) if row and row.info else {}
	if state == "ready":
		return {"state": "ready", "reason": None, "w": row.width, "h": row.height, "meta": meta}
	return {"state": "pending" if state == "pending" else "none", "reason": row.reason if row else None, "w": None,
		"h": None, "meta": meta}
