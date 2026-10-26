"""The kinds of source a preview is asked for, as a registry (P3-75, design §15.3; R-33).

Each kind turns the id a viewer sends into the bytes' holder and key, or into None when the viewer may not see that
source: the endpoint then answers one "not found" for missing, unreadable and unknown alike. A kind checks with the
source's own rule, never a weaker one:

- ``attachment``: a sent Discuss Attachment, through the viewer's visible messages and the file's download rule (never
  a File id; a linked file revised since shows the revision that was sent, §15.3);
- ``file``: a project File, through ``has_permission`` (clients are never given File ids, so in practice it is the
  team's: the Files list);
- ``board``: a Whiteboard, through its read rule (clients read boards marked client visible). Its picture is the
  editor's own export after a save, so no job ever draws it (``Target.server`` False);
- ``approval copy`` (P3-77, approvals design §4.3): ``<request>:<key>``, a request's frozen copy, through the request's
  own read rule (approvals.read), never its record's. Its holder is the frozen copy (``COPY``, named by its SHA-256),
  which the job reads from the frozen folder.

A new kind is one ``register`` call and one row in test_previews' permission table, which fails for a kind that has none.
"""

from collections.abc import Callable
from dataclasses import dataclass

import frappe

from construction_core.permissions import switches_once


@dataclass(frozen=True)
class Target:
	"""What a preview is made of and stored as: the source row that holds the bytes, and its key."""

	source_type: str  # "File" or "Whiteboard"
	source_name: str
	key: str  # the content hash, or "v<version>" for a board
	ext: str
	scanned: bool = False  # the bytes passed the virus scan when they arrived
	legacy: str | None = None  # a chat photo's preview from its clean_image decode (P3-65), served first
	server: bool = True  # the thumbs job draws it; False: its own writer stores it (a board's snapshot from the editor)


@dataclass(frozen=True)
class Source:
	kind: str
	resolve: Callable[[str, str], Target | None]  # (id, viewer) -> the target the viewer may see, else None


SOURCES: dict[str, Source] = {}
COPY = "Approval Copy"  # a frozen copy's source type (approvals.frozen)


def register(source: Source) -> None:
	SOURCES[source.kind] = source


def resolve(kind: str, ident, viewer: str) -> Target | None:
	source = SOURCES.get(kind)
	if not source or not isinstance(ident, str) or not ident or len(ident) > 140:
		return None
	try:
		with switches_once():
			return source.resolve(ident, viewer)
	except (frappe.DoesNotExistError, frappe.PermissionError):
		# a record gone between the read and the check: "not found", and none of its words (its id) in the answer
		frappe.clear_last_message()
		frappe.local.message_log = []
		return None


# --- the kinds ------------------------------------------------------------------------------------------------------


def attachment(ident: str, viewer: str) -> Target | None:
	from construction_core.discuss import media

	row = frappe.db.get_value(media.DOCTYPE, ident, ["message", "file", "state", "content_hash", "has_preview", "ext",
		"kind", "source", "preview_state"], as_dict=True)
	if not row or row.state != "Sent" or not row.message or not row.file or not (row.content_hash or "").isalnum():
		return None
	current = frappe.db.get_value("File", row.file, ["content_hash", "cc_trashed"], as_dict=True)
	if not current or current.cc_trashed:  # deleted, or in the bin: the bin removes previews (§15.3)
		return None
	visible = frappe.get_list("Discuss Message", filters={"name": row.message}, pluck="name", limit=1, user=viewer)
	if not visible or not frappe.has_permission("File", "read", doc=row.file, user=viewer, throw=False):
		return None
	holder = row.file
	if current.content_hash != row.content_hash:  # revised since it was sent
		holder = frappe.db.get_value("File", {"cc_version_of": row.file, "content_hash": row.content_hash}, "name") or holder
	legacy = media.preview_path(row.content_hash) if row.has_preview and not row.preview_state else None
	return Target("File", holder, row.content_hash, row.ext or "", scanned=row.source in ("Upload", "Copy"),
		legacy=legacy)


def file(ident: str, viewer: str) -> Target | None:
	from construction_core.discuss.media import ext_of

	f = frappe.db.get_value("File", ident, ["name", "file_name", "is_folder", "cc_project", "cc_trashed", "content_hash",
		"owner"], as_dict=True)
	if not f or f.is_folder or not f.cc_project or f.cc_trashed or not (f.content_hash or "").isalnum():
		return None
	if not frappe.has_permission("File", "read", doc=f.name, user=viewer, throw=False):
		return None
	client_stored = frappe.get_cached_value("User", f.owner, "user_type") == "Website User"  # scanned when stored
	return Target("File", f.name, f.content_hash, ext_of(f.file_name), scanned=client_stored)


def board(ident: str, viewer: str) -> Target | None:
	version = frappe.db.get_value("Whiteboard", ident, "version")
	if version is None or not frappe.has_permission("Whiteboard", "read", doc=ident, user=viewer, throw=False):
		return None
	return Target("Whiteboard", ident, f"v{int(version or 0)}", "png", scanned=True, server=False)


def approval_copy(ident: str, viewer: str) -> Target | None:
	from construction_core.approvals import frozen, read
	from construction_core.discuss.media import ext_of

	request, _sep, key = ident.partition(":")
	doc = read.readable(request) if viewer == frappe.session.user else None  # the rule reads the session's user
	entry = frozen.entry_of(doc, key) if doc else None
	if not entry:
		return None
	return Target(COPY, entry["shown_sha256"], entry["shown_sha256"], ext_of(entry.get("name") or ""))


register(Source("attachment", attachment))
register(Source("file", file))
register(Source("board", board))
register(Source("approval copy", approval_copy))
