"""StorageProvider (ARCHITECTURE §2.6, D-078, D-079, DR-4).

Core code stores files only through ``get_storage()``. ``FileStorage`` (core ``File``) is the default; an
optional adapter such as ``ws_drive`` may provide ``DriveStorage`` with the same method names, which follow
Drive's real API (S2, D-016): ``ensure_path``, ``put``, ``get_url``, ``grant`` / ``revoke``, ``delete``, and
``list_folder`` (P2-04, the shell's Files section).

Access is our model (DR-5): project membership plus ``cc_client_visible``, enforced by
``construction_core.permissions``. Every write emits a storage event through ``emit()`` (DR-4).
"""

from __future__ import annotations

import os
import re
from io import BytesIO

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import get_files_path

from construction_core.core.events import emit

PROJECTS_ROOT = "Projects"  # project trees live at Projects/<project> (workspace.root_path)
ROOT = "Home"
# P3-07 (D-140, D-158): where the files a client sends land, under the project's 06_Client folder. Only the project's
# clients add files here (permissions.validate_file); staff share one by making it client visible.
CLIENT_INBOX = "06_Client/From client"  # sent in Files: seen by its sender and the team until shared
CLIENT_CHAT = "06_Client/Discussion files"  # sent in a conversation: attached to its thread, seen by that conversation
CLIENT_FOLDERS = (CLIENT_INBOX, CLIENT_CHAT)
# P3-65 (design §3.2, FIT-13): the files of Team-room conversations, under the project's root, made by the app on first
# use (and by a patch for existing projects), never by the Folder Template, so a set-up edit cannot remove it. Never
# shared: its files are the team's.
INTERNAL_CHAT = "Discussion files"
IMAGE_TYPES = ("jpg", "jpeg", "png", "webp")
MAX_PIXELS = 50_000_000  # a phone's 48 or 50 megapixel mode; checked before any image is decoded


def write_atomic(path: str, content: bytes):
	"""Replace a file's bytes in place: a reader sees the old bytes or the new ones, never half a file."""
	tmp = f"{path}.cc-tmp-{frappe.generate_hash(length=8)}"
	with open(tmp, "wb") as fh:
		fh.write(content)
	os.replace(tmp, path)


def file_stem(text: str) -> str:
	"""A disk name part: ASCII letters, digits, - and _ only, at most 80 characters."""
	return re.sub(r"[^A-Za-z0-9_-]", "_", text or "")[:80] or "file"


def own_path(stem: str, ext: str, content: bytes) -> str:
	"""Write ``content`` at a new private path that no other File uses, and return its URL. The name is created
	exclusively, so an existing file is never overwritten, and a rollback removes it. ``ext`` is like ``.pdf``."""
	ext = re.sub(r"[^A-Za-z0-9]", "", (ext or "").lstrip("."))[:10]
	for _attempt in range(5):
		name = f"{file_stem(stem)}-{frappe.generate_hash(length=12)}{'.' + ext if ext else ''}"
		path = get_files_path(name, is_private=True)
		try:
			fh = open(path, "xb")
		except FileExistsError:
			continue
		frappe.db.after_rollback.add(lambda path=path: os.path.exists(path) and os.remove(path))
		with fh:
			fh.write(content)
		return f"/private/files/{name}"
	frappe.throw(_("The file could not be stored. Please try again."))


PREVIEW_PX = 400  # a chat photo's preview, on its long edge (design §3.2, §15.1)


def clean_image(content: bytes, ext: str) -> bytes:
	"""A client image rebuilt from its pixels: no EXIF, XMP, text chunks or trailing bytes, the colour profile kept,
	turned upright. Frappe's own strip keeps XMP (and the GPS in it) when an image has no EXIF (measured, P3-07)."""
	return clean_photo(content, ext, preview=False).content


def clean_photo(content: bytes, ext: str, preview: bool = True) -> frappe._dict:
	"""clean_image's one decode, and what a chat photo keeps of it (P3-65, R-32 §15.8): ``content`` the cleaned bytes,
	``width`` and ``height`` upright, ``taken`` the camera's capture time read before the re-encode (never the place:
	no other tag is read), and with ``preview`` a WebP of at most PREVIEW_PX px with no metadata (``preview``,
	``preview_w``, ``preview_h``). No second parser sees the bytes."""
	from PIL import Image, ImageOps

	with Image.open(BytesIO(content)) as source:
		if source.width * source.height > MAX_PIXELS:
			frappe.throw(_("The image is larger than 50 megapixels. Send a smaller copy."))
		taken = _capture_time(source)
		icc = source.info.get("icc_profile")
		transparent = "transparency" in source.info  # a palette or tRNS transparency is pixels, not metadata
		image = ImageOps.exif_transpose(source)
		if transparent and ext in ("png", "webp"):
			image = image.convert("RGBA")
		image.info = {}  # nothing of the original's metadata may be written back
		keep = {"icc_profile": icc} if icc else {}
		out = BytesIO()
		if ext in ("jpg", "jpeg"):
			if image.mode not in ("RGB", "L", "CMYK"):
				image = image.convert("RGB")
			image.save(out, "JPEG", quality=92, **keep)
		elif ext == "png":
			image.save(out, "PNG", optimize=True, **keep)
		else:
			image.save(out, "WEBP", quality=92, **keep)
		result = frappe._dict(content=out.getvalue(), width=image.width, height=image.height, taken=taken)
		if preview:
			result.update(_preview(image))
	return result


def _preview(image) -> dict:
	"""A WebP of at most PREVIEW_PX px on its long edge, from pixels already decoded, with no metadata at all."""
	thumb = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P", "PA") else "RGB")
	thumb.thumbnail((PREVIEW_PX, PREVIEW_PX))
	thumb.info = {}
	out = BytesIO()
	thumb.save(out, "WEBP", quality=80)
	return {"preview": out.getvalue(), "preview_w": thumb.width, "preview_h": thumb.height}


def _capture_time(source):
	"""The EXIF DateTimeOriginal (else DateTime) as a naive datetime, or None. Bad EXIF never fails an image."""
	from datetime import datetime

	try:
		exif = source.getexif()
		raw = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)
		taken = datetime.strptime(str(raw).replace(chr(0), "").strip()[:19], "%Y:%m:%d %H:%M:%S") if raw else None
	except Exception:
		return None
	return taken if taken and 1990 <= taken.year <= datetime.now().year + 1 else None


class StorageProvider:
	"""The contract. One test suite (tests/test_providers.py) runs against every implementation."""

	name = "abstract"

	def ensure_path(self, path: str, project: str | None = None) -> str:
		"""Idempotently create the folder chain ``a/b/c`` under the root; return the leaf folder's id."""
		raise NotImplementedError

	def put(self, path: str, file_name: str, content: bytes, project: str | None = None,
			client_visible: bool = False) -> str:
		"""Store ``content`` as ``file_name`` in folder ``path``; return the file id. Always private."""
		raise NotImplementedError

	def put_own(self, path: str, file_name: str, content: bytes, project: str, *, client_visible: bool = False,
			attach: tuple[str, str] | None = None, cleaned: bool = False) -> str:
		"""Store a file a client sent (P3-07) at a path of its own, never sharing bytes with another file; return its
		id. The caller has checked the user's right and the content (DR-5); Frappe's own upload checks run again here,
		because this route skips them. ``attach`` defaults to the project."""
		raise NotImplementedError

	def get_url(self, file_id: str) -> str:
		raise NotImplementedError

	def grant(self, file_id: str, user: str, level: str = "read") -> None:
		raise NotImplementedError

	def revoke(self, file_id: str, user: str) -> None:
		raise NotImplementedError

	def set_client_visible(self, file_id: str, visible: bool) -> None:
		raise NotImplementedError

	def delete(self, file_id: str) -> None:
		"""Trash, never hard delete: the file leaves every listing but stays recoverable."""
		raise NotImplementedError

	def move(self, file_id: str, folder_id: str) -> None:
		"""Put a file in another folder of the same project (P3-41). The caller has checked both (DR-5)."""
		raise NotImplementedError

	def is_trashed(self, file_id: str) -> bool:
		raise NotImplementedError

	def list_folder(self, folder_id: str) -> list[dict]:
		"""The folder's direct entries that are not trashed, folders first, then by name. Each entry: ``name`` (the
		id), ``file_name``, ``is_folder``, ``file_size``, ``modified``, ``owner``, ``client_visible``, ``url``.
		No permission filter here: callers check each entry for the session user (DR-5)."""
		raise NotImplementedError


class FileStorage(StorageProvider):
	"""Core ``File`` storage: local private files, covered by the site backups (D-078)."""

	name = "file"

	def ensure_path(self, path: str, project: str | None = None) -> str:
		parent = ROOT
		seen = []
		for part in [p.strip() for p in path.split("/") if p.strip()]:
			seen.append(part)
			# Folders above Projects/<project> are shared by every project and belong to none.
			owner = project if project and seen[:2] == [PROJECTS_ROOT, project] else None
			existing = frappe.db.get_value("File", {"is_folder": 1, "folder": parent, "file_name": part}, "name")
			if not existing:
				folder = frappe.get_doc(
					{"doctype": "File", "file_name": part, "is_folder": 1, "folder": parent, "cc_project": owner}
				)
				# ignore_permissions: folders are provisioned by the system for a project, not by a user's rights.
				existing = self._make_folder(folder)
			parent = existing
		return parent

	def _make_folder(self, folder) -> str:
		"""Get or create (P3-65): a folder's name is its path, so two requests making the same folder at once (the first
		two chat sends of a new project) meet the primary key. The loser takes the winner's folder, by that name; its own
		insert is rolled back to a savepoint, so the rest of its request stands."""
		point = "cc_folder_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(point)
		try:
			folder.insert(ignore_permissions=True)
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			frappe.db.rollback(save_point=point)
			frappe.clear_last_message()
			if not folder.name:
				raise
			return folder.name
		frappe.db.release_savepoint(point)
		emit("storage.folder_created", folder)
		return folder.name

	def put(self, path, file_name, content, project=None, client_visible=False):
		folder = self.ensure_path(path, project)
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": file_name,
				"folder": folder,
				"content": content,
				"is_private": 1,
				"cc_project": project,
				"cc_client_visible": 1 if client_visible else 0,
				# Attached to its Project, so Frappe's own File rule (can the user read the Project?) agrees with
				# ours; an unattached private file is readable only by its owner.
				**({"attached_to_doctype": "Construction Project", "attached_to_name": project} if project else {}),
			}
		)
		f.insert()  # permission-checked as the current user (DR-5)
		emit("storage.file_added", f)
		return f.name

	def put_own(self, path, file_name, content, project, *, client_visible=False, attach=None, cleaned=False):
		"""``cleaned``: an image the caller has already rebuilt with clean_photo (a chat file, P3-65), not decoded twice."""
		from frappe.core.api.file import get_max_file_size
		from frappe.utils.file_manager import MaxFileSizeReachedError
		from frappe.utils.pdf import pdf_contains_js

		folder = self.ensure_path(path, project)
		base, _dot, ext = file_name.rpartition(".")
		ext = ext.lower()
		if ext in IMAGE_TYPES and not cleaned:
			content = clean_image(content, ext)
		if len(content) > get_max_file_size():
			raise MaxFileSizeReachedError
		if ext == "pdf":  # Frappe's own check, kept for parity (client_files checks more); unreadable is refused
			try:
				scripted = pdf_contains_js(content)
			except Exception:
				frappe.throw(_("This PDF could not be read."))
			if scripted:
				frappe.throw(_("This PDF contains scripts or interactive content, which we do not accept."))
		doctype, name = attach or ("Construction Project", project)
		f = frappe.get_doc({
			"doctype": "File", "file_name": file_name, "file_url": own_path(base, ext, content), "is_private": 1,
			"folder": folder, "cc_project": project, "cc_client_visible": 1 if client_visible else 0,
			"content_hash": get_content_hash(content), "file_size": len(content),
			"attached_to_doctype": doctype, "attached_to_name": name,
		})
		f.flags.copy_from_existing_file = True  # our own new path: Frappe must not point it at an identical file
		# ignore_permissions: the caller checked the user's right (DR-5), and validate_file allows exactly the one
		# insert the caller described (permissions.client_upload_shape).
		f.insert(ignore_permissions=True)
		if f.file_size != len(content):  # File.validate takes a file_size sent with the request over the real one
			f.db_set("file_size", len(content), update_modified=False)
		emit("storage.file_added", f)
		return f.name

	def get_url(self, file_id):
		return frappe.db.get_value("File", file_id, "file_url")

	def grant(self, file_id, user, level="read"):
		# A DocShare; construction_core.permissions.validate_share allows it only for members of the file's
		# project, and for a client only on a client-visible file.
		frappe.share.add("File", file_id, user, read=1, write=1 if level == "write" else 0)
		emit("storage.access_granted", doctype="File", name=file_id, version=f"{user}:{level}")

	def revoke(self, file_id, user):
		frappe.share.remove("File", file_id, user)
		emit("storage.access_revoked", doctype="File", name=file_id, version=f"{user}:{frappe.utils.now()}")

	def set_client_visible(self, file_id, visible):
		f = frappe.get_doc("File", file_id)
		f.cc_client_visible = 1 if visible else 0
		f.save()  # validate_file: only staff members may change it
		emit("storage.visibility_changed", f)

	def delete(self, file_id):
		f = frappe.get_doc("File", file_id)
		f.check_permission("write")
		f.db_set("cc_trashed", 1)
		emit("storage.file_trashed", f)

	def move(self, file_id, folder_id):
		f = frappe.get_doc("File", file_id)
		f.folder = folder_id
		f.save()  # permission-checked as the current user; validate_file keeps it in its project (DR-5, DR-6)
		emit("storage.file_moved", f)

	def is_trashed(self, file_id):
		return bool(frappe.db.get_value("File", file_id, "cc_trashed"))

	def list_folder(self, folder_id):
		# P3-43 (D-301): a file's earlier versions are not files of the folder; they show in its Versions tab
		rows = frappe.get_all("File", filters={"folder": folder_id, "cc_trashed": ["in", [0, None]],
				"cc_version_of": ["is", "not set"]},
			fields=["name", "file_name", "is_folder", "file_size", "modified", "owner", "cc_client_visible", "file_url",
				"cc_rev", "content_hash"],
			order_by="is_folder desc, file_name asc")
		return [{"name": r.name, "file_name": r.file_name, "is_folder": r.is_folder, "file_size": r.file_size,
			"modified": r.modified, "owner": r.owner, "client_visible": r.cc_client_visible, "url": r.file_url,
			"rev": r.cc_rev or "A", "content_hash": r.content_hash or ""}
			for r in rows]


def get_storage() -> StorageProvider:
	"""The site's storage provider: ``cc_storage_provider`` in site config (a class path), else FileStorage."""
	path = frappe.conf.get("cc_storage_provider")
	return frappe.get_attr(path)() if path else FileStorage()
