"""One pipeline for every chat file (P3-65; design §3.2, §3.3, rule 7; D-366, D-389, D-390).

Every file a message carries passes the same checks, whoever sends it and wherever it goes: the type list, the
signature, the size (and, for a client, the project's daily cap), the structure, the ClamAV scan that fails closed,
then an image is rebuilt from its pixels with no EXIF, XMP or GPS (``storage.clean_photo``). Staff files in the Team
room are checked too (D-366). The order is send_file's (§13.5 item 8).

- **stage**: the checked bytes wait outside the site's files (``<site>/private/cc_chat_staging``) beside a Pending
  Discuss Attachment of the uploader. No File exists yet, so a waiting file is in no Files list, never shared, never a
  client's, and no answer names a File id (SEC-4, FIT-11).
- **A photo's preview** (R-32, §15.8) comes from the same decode: a WebP of at most 400 px with no metadata, stored by
  content hash under ``<site>/private/thumbs`` (outside the backups, D-421), served only through the chat's preview
  read, which checks its message and source file (SEC-8). Other types get no preview until P3-75.
- **The capture time** is read before the re-encode, from the camera's EXIF time, or from the browser when its own
  shrink dropped the EXIF (the place is never kept, L-16).
- **materialize**: at send the File is made in the conversation's folder under a claim shape that validate_file
  accepts exactly once (D-390, amending D-158): ``06_Client/Discussion files``, shared with the conversation, for a
  Client message; the internal ``Discussion files`` folder, never shared, for the Team room.
- **Share and send** (D-367, D-390) stages a checked copy of a project file through this same pipeline; the original
  is not changed and not shared. **A link** (the Team room, or a client's own readable file) makes no copy.
- **purge**: Pending rows older than 24 hours are deleted with their bytes, a real delete, not the bin (D-389); waiting
  bytes no row names (a request that died mid-upload) go after 24 hours too, and so do Held rows (a file request's
  uploads, P3-71) that no item of an Open request names any more.
- **Two uploads at a time** per user (FIT-14).
- **A voice note** (P3-67) is staged the same way, its row holding the length, type and codec its container states.
"""

import os
import time
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import add_to_date, get_datetime, get_site_path, now_datetime

from construction_core import client_files
from construction_core.discuss import rows
from construction_core.providers.storage import (
	CLIENT_CHAT,
	IMAGE_TYPES,
	INTERNAL_CHAT,
	clean_photo,
	get_storage,
	write_atomic,
)

DOCTYPE = "Discuss Attachment"
STAGING = "cc_chat_staging"
THUMBS = "thumbs"
PREVIEW_SPEC = "p400"  # P3-75's Preview Image keys previews by hash and spec too
PENDING_HOURS = 24
AT_ONCE, SLOT_TTL = 2, 300  # uploads at a time per user; a crashed upload frees its slot after SLOT_TTL seconds
REQUEST_SECONDS = 110.0  # the scan gets what is left of the request's 120 s, keeping 10 s to store (P3-07 audit S2)
KINDS = {"jpg": "photo", "jpeg": "photo", "png": "photo", "webp": "photo", "pdf": "pdf", "docx": "office",
	"xlsx": "office", "pptx": "office", "doc": "office", "xls": "office", "ppt": "office", "dwg": "drawing",
	"dxf": "drawing", "rvt": "model", "rfa": "model", "ifc": "model", "skp": "model"}
PURGE_BATCH = 500


def kind_of(ext: str) -> str:
	"""The card's kind (§15.6): photo, pdf, office, drawing, model, or file for any other type."""
	return KINDS.get((ext or "").lower(), "file")


def ext_of(file_name: str) -> str:
	return (file_name or "").rpartition(".")[2].lower() if "." in (file_name or "") else ""


# --- the checks -----------------------------------------------------------------------------------------------------


def checked(ext: str, content: bytes, project: str, *, started: float, client: bool, facts: dict | None = None) -> bytes:
	"""The checks, in send_file's order from its step 4: type, signature, size, a client's daily cap, structure, scan.
	Returns the bytes as checked. Nothing is stored before the scan has answered "OK". ``facts``: filled with what the
	structure check read (a voice note's ``voice``), so the stage does not read the file again."""
	client_files.check_type(ext)
	if not content:
		frappe.throw(_("The file is empty"))
	client_files.check_signature(ext, content)
	limit = client_files.client_limit()
	if len(content) > limit:
		frappe.throw(_("The file is larger than {0}").format(client_files.size_text(limit)))
	if client:
		client_files.check_daily_cap(project, len(content), chat=True)
	structure = client_files.check_structure(ext, content)
	if facts is not None:
		facts["voice"] = structure
	client_files.scan(content, project=project, budget=max(5.0, REQUEST_SECONDS - (time.monotonic() - started)))
	return content


@contextmanager
def slot(user: str):
	"""At most AT_ONCE uploads of one user at a time (FIT-14). Each upload holds a token in a set scored by its start
	time, freed when it ends however it ends; a token older than SLOT_TTL (a worker killed mid-upload) no longer counts,
	so a crash never blocks the user's uploads for more than SLOT_TTL."""
	key = frappe.cache.make_key(f"cc:chat_upload:active:{user}")
	token, now = frappe.generate_hash(length=12), time.time()
	frappe.cache.zremrangebyscore(key, "-inf", now - SLOT_TTL)
	frappe.cache.zadd(key, {token: now})
	frappe.cache.expire(key, SLOT_TTL)
	try:
		if frappe.cache.zcard(key) > AT_ONCE:
			frappe.throw(_("Two files are uploading. Wait for one to finish, then try again."),
				frappe.RateLimitExceededError)
		yield
	finally:
		frappe.cache.zrem(key, token)


# --- staging --------------------------------------------------------------------------------------------------------


def stage(t, uploader: str, display: str, ext: str, content: bytes, *, source: str = "Upload",
		source_file: str | None = None, rev: str | None = None, taken=None, voice=None) -> str:
	"""A Pending attachment of ``uploader`` in thread ``t``, with the checked bytes waiting outside the site's files. An
	image is rebuilt here, and its preview made from the same decode."""
	from frappe.core.api.file import get_max_file_size
	from frappe.utils.file_manager import MaxFileSizeReachedError

	values = {"uploader": uploader, "source": source, "source_file": source_file, "file_name": display, "ext": ext,
		"kind": kind_of(ext), "rev": rev}
	if ext in IMAGE_TYPES:
		photo = clean_photo(content, ext)
		content = photo.content
		values.update(width=photo.width, height=photo.height, taken_on=photo.taken or taken)
	elif ext in client_files.AUDIO_TYPES:  # P3-67: only the voice upload stages audio (client_files.voice_types)
		values.update(voice_values(ext, content, voice))
	if len(content) > get_max_file_size():
		raise MaxFileSizeReachedError(_("This image is too large to store once its hidden data is removed. Send a "
			"smaller copy."))
	digest = get_content_hash(content)
	if ext in IMAGE_TYPES:
		_keep_preview(digest, photo.preview)
		values.update(has_preview=1, preview_w=photo.preview_w, preview_h=photo.preview_h)
	values.update(content_hash=digest, file_size=len(content), staged=_write_staged(ext, content),
		expires_on=add_to_date(now_datetime(), hours=PENDING_HOURS))
	return rows.insert(DOCTYPE, values, thread=t.name)


def voice_values(ext: str, content: bytes, voice=None) -> dict:
	"""A voice note's row: the length, type and codec the bounded reader found when it checked the file (design §3.6,
	SEC-16); the browser's own claims are never stored. ``voice``: that reading (media.checked's facts)."""
	from construction_core import audio

	if voice is None or voice.ext != ext:
		voice = audio.check(ext, content)  # only a caller that skipped media.checked reads it here
	return {"kind": "voice", "voice_length": voice.length, "voice_type": voice.mime, "voice_codec": voice.codec}


def chat_made(file: str | None) -> bool:
	"""Whether a conversation made this File (an upload or a checked copy, not a linked project file): a record of what
	was sent, kept as it was sent. P3-67 audit S3, S4: no new revision, no new address, name or bytes."""
	return bool(file) and bool(frappe.db.exists(DOCTYPE, {"file": file, "source": ["in", ("Upload", "Copy")]}))


def refuse_chat_made(file: str | None) -> None:
	if chat_made(file):
		frappe.throw(_("A file sent in a conversation stays as it was sent."), frappe.PermissionError)


def link(t, uploader: str, f) -> str:
	"""A Pending attachment that links a project file, with no copy: the Team room's Attach from Files (never shared,
	recheck N-3), or a client's own readable file (Ask about this file)."""
	from construction_core.files import versions

	from construction_core.discuss.registry import sender_of

	ext = ext_of(f.file_name)
	values = {"uploader": uploader, "source": "Link", "file": f.name, "file_name": f.file_name, "ext": ext,
		"kind": kind_of(ext), "file_size": f.file_size, "content_hash": f.content_hash,
		"rev": versions.current_rev(f.name), "expires_on": add_to_date(now_datetime(), hours=PENDING_HOURS)}
	if ext in IMAGE_TYPES and sender_of(uploader) == "staff":  # a staff link's photo gets its preview too (staff only)
		values.update(link_preview(f, ext))
	return rows.insert(DOCTYPE, values, thread=t.name)


def link_preview(f, ext: str) -> dict:
	"""A linked image's preview, from its own bytes through the same checks and decode as a sent photo (the type's
	signature and header, then clean_photo; nothing of the file is changed or stored but the preview). A file that
	fails them, or is too large to decode here, simply has no preview: a link never fails for its preview."""
	try:
		content = _bytes_of(f.name)
		if not content or len(content) > client_files.client_limit():
			return {}
		photo = _decoded(content, ext)
		digest = get_content_hash(content)
		_keep_preview(digest, photo.preview)
	except Exception:
		frappe.clear_last_message()
		return {}
	return {"content_hash": digest, "has_preview": 1, "preview_w": photo.preview_w, "preview_h": photo.preview_h,
		"width": photo.width, "height": photo.height, "taken_on": photo.taken}


def rebuild_preview(file: str, digest: str, ext: str) -> str | None:
	"""A sent photo's preview made again from the bytes that were sent, the same hash key (a site restored from a backup
	has no previews: they are not backed up, D-421). The bytes are the File's own, or the version row's that holds that
	hash (a linked file revised since). None when they are gone or fail the checks."""
	path = preview_path(digest)
	try:
		content = _bytes_of(file)
		if content and get_content_hash(content) != digest:
			version = frappe.db.get_value("File", {"cc_version_of": file, "content_hash": digest}, "name")
			content = _bytes_of(version) if version else None
		if not path or not content or get_content_hash(content) != digest:
			return None
		photo = _decoded(content, ext)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		write_atomic(path, photo.preview)
	except Exception:
		frappe.clear_last_message()
		return None
	return path


def _decoded(content: bytes, ext: str):
	client_files.check_signature(ext, content)
	client_files.check_structure(ext, content)  # the header only: format, 50 megapixels, one frame
	return clean_photo(content, ext)


def _bytes_of(file: str | None) -> bytes | None:
	if not file or not frappe.db.exists("File", file):
		return None
	content = frappe.get_doc("File", file).get_content()
	return content.encode() if isinstance(content, str) else content


def _write_staged(ext: str, content: bytes) -> str:
	"""The waiting bytes at a new name under the staging folder; a rollback removes them. Returns the name."""
	folder = get_site_path("private", STAGING)
	os.makedirs(folder, exist_ok=True)
	for _attempt in range(5):
		name = f"{frappe.generate_hash(length=20)}.{ext}"
		path = os.path.join(folder, name)
		try:
			fh = open(path, "xb")
		except FileExistsError:
			continue
		frappe.db.after_rollback.add(lambda path=path: os.path.exists(path) and os.remove(path))
		with fh:
			fh.write(content)
		return name
	frappe.throw(_("The file could not be stored. Please try again."))


def staged_path(name: str | None) -> str | None:
	"""The waiting bytes of a row, only ever inside the staging folder (a stored name is a bare file name)."""
	if not name or os.path.basename(name) != name or name.startswith("."):
		return None
	return get_site_path("private", STAGING, name)


def preview_path(digest: str | None) -> str | None:
	if not digest or not digest.isalnum():
		return None
	return get_site_path("private", THUMBS, f"{digest}-{PREVIEW_SPEC}.webp")


def _keep_preview(digest: str, preview: bytes) -> None:
	"""Previews with the same hash share one stored file (§15.3); one made in this request goes with a rollback."""
	path = preview_path(digest)
	if os.path.exists(path):
		return
	os.makedirs(os.path.dirname(path), exist_ok=True)
	write_atomic(path, preview)
	frappe.db.after_rollback.add(lambda: _drop_unused_preview(digest, path))


def _drop_unused_preview(digest: str, path: str) -> None:
	if os.path.exists(path) and not frappe.db.exists(DOCTYPE, {"content_hash": digest, "has_preview": 1}):
		os.remove(path)


# --- the send -------------------------------------------------------------------------------------------------------


def materialize(row, message) -> str:
	"""The File of a claimed upload or copy, made in the message's conversation folder under the claim shape, from the
	bytes that were checked. The waiting bytes are removed only after the commit, so a send that rolls back can be
	sent again."""
	from frappe.utils.file_manager import MaxFileSizeReachedError

	from construction_core.workspace import client_folders, root_path

	path = staged_path(row.staged)
	if not path or not os.path.exists(path):
		frappe.throw(_("A file is no longer waiting to be sent. Add it again."))
	with open(path, "rb") as fh:
		content = fh.read()
	if get_content_hash(content) != row.content_hash:
		frappe.throw(_("A file is no longer waiting to be sent. Add it again."))
	shared = message.audience == "Client" and not message.staff_only
	store = get_storage()
	if shared:
		folder, place = client_folders(message.project)["chat"], f"{root_path(message.project)}/{CLIENT_CHAT}"
		if not folder:
			frappe.throw(_("This project cannot receive files yet. Ask the project team."))
	else:
		place = f"{root_path(message.project)}/{INTERNAL_CHAT}"
		folder = store.ensure_path(place, message.project)  # made on first use (FIT-13)
	# validate_file allows exactly this one insert, as described here (permissions.client_upload_shape, D-390).
	frappe.flags.cc_client_upload = frappe._dict(project=message.project, folder=folder, visible=1 if shared else 0,
		attach=("Discuss Thread", message.thread), consumed=False)
	try:
		name = store.put_own(place, row.file_name, content, message.project, client_visible=shared,
			attach=("Discuss Thread", message.thread), cleaned=True)
	except MaxFileSizeReachedError:
		frappe.throw(_("This file is too large to store. Send a smaller copy."))
	finally:
		frappe.flags.cc_client_upload = False
	frappe.db.after_commit.add(lambda: os.path.exists(path) and os.remove(path))
	return name


# --- removal --------------------------------------------------------------------------------------------------------


def remove(row) -> None:
	"""Delete one Pending row and its waiting bytes: a real delete, not the bin (D-389). The bytes go after the commit."""
	frappe.db.delete(DOCTYPE, {"name": row.name, "state": "Pending"})
	path = staged_path(row.staged)
	digest = row.content_hash if row.has_preview else None

	def after():
		if path and os.path.exists(path):
			os.remove(path)
		if digest:
			_drop_unused_preview(digest, preview_path(digest))

	frappe.db.after_commit.add(after)


def purge() -> int:
	"""The hourly job (D-389): Pending rows whose 24 hours have passed, and Held rows no Open request's item names, deleted
	with their bytes. Returns how many."""
	found = frappe.get_all(DOCTYPE, filters={"state": "Pending", "expires_on": ["<", now_datetime()]},
		fields=["name", "state", "staged", "content_hash", "has_preview"], limit=PURGE_BATCH, order_by="expires_on asc")
	found += _unowned_held()
	for row in found:
		frappe.db.delete(DOCTYPE, {"name": row.name, "state": row.state})
		path = staged_path(row.staged)
		if path and os.path.exists(path):
			os.remove(path)  # an expired or unowned row is never claimed: its bytes may go at once
		if row.has_preview:
			_drop_unused_preview(row.content_hash, preview_path(row.content_hash))
	return len(found) + sweep_orphans()


def _unowned_held() -> list:
	"""Held uploads (P3-71) that no item of an Open request names: a request deleted in Desk, or one missed by its cancel.
	Nothing can accept or review them, so they go like any unsent file. A raw statement: the item's attachment is NULL
	while it waits, which NOT IN would turn into no rows at all."""
	return frappe.db.sql("""select a.name, a.state, a.staged, a.content_hash, a.has_preview from `tabDiscuss Attachment` a
		where a.state = 'Held' and not exists (select 1 from `tabFile Request Item` i join `tabFile Request` r
			on r.name = i.parent where i.attachment = a.name and r.status = 'Open') limit %s""", (PURGE_BATCH,), as_dict=True)


def sweep_orphans() -> int:
	"""Waiting bytes that no row names and that are older than PENDING_HOURS: left by a request that died before its
	commit or rollback could remove them (a worker killed mid-upload). Deleted like any unsent file (D-389)."""
	folder = get_site_path("private", STAGING)
	if not os.path.isdir(folder):
		return 0
	cutoff = time.time() - PENDING_HOURS * 3600
	old = [e.name for e in os.scandir(folder) if e.is_file() and e.stat().st_mtime < cutoff]
	if not old:
		return 0
	named = set(frappe.get_all(DOCTYPE, filters={"staged": ["in", old]}, pluck="staged"))
	gone = [n for n in old if n not in named]
	for n in gone:
		os.remove(os.path.join(folder, n))
	return len(gone)


def expired(row) -> bool:
	return not row.expires_on or get_datetime(row.expires_on) <= now_datetime()
