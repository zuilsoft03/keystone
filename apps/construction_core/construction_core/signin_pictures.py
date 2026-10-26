"""Sign-in pictures (P3-34, R-16; D-272…D-275, design §12): renders a project's managers mark for the public client
sign-in (LoginB).

The sign-in page is public, so nothing reaches it by itself (D-272): a manager (``manage_clients`` on the project) picks
an image from the project's own files and marks it. The server keeps a public copy rebuilt from the pixels (no EXIF,
XMP or GPS, which could carry the staff-only site location, D-157; at most 2400 px wide) and only that copy is ever sent
to a visitor. Every guest read checks, at that moment, that the picture is still marked, its project still exists and
its source file is not in the bin, so unmarking or trashing removes it at once.

What a visitor gets (D-273): the boot of the sign-in page (``for_signin``) lists the pictures of the project its
``redirect-to`` names when that project has any, else every marked picture (the slideshow). An unknown project and one
without pictures get the same list. The one thing a link adds is which public picture belongs to a project the visitor
already named. A caption shows only when the manager typed one (D-274).
"""

import hashlib
import os
import re
from io import BytesIO
from urllib.parse import unquote

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, now_datetime
from werkzeug.wrappers import Response

from construction_core.permissions import is_client
from construction_core.providers.storage import IMAGE_TYPES, MAX_PIXELS, get_storage

DOCTYPE = "Signin Picture"
FOLDER = "Sign-in pictures"  # Home/Sign-in pictures: the public copies, in no project
RENDERS = "02_Design/Renders"  # where an uploaded render is kept in its project (D-281)
MAX_SOURCE = 15 * 1024 * 1024
MAX_WIDTH = 2400
PER_PROJECT = 6
SLIDESHOW = 12
CAPTION = 80
TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
FORMATS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
PORTAL_PATH = re.compile(r"^/portal/([^/?#]+)")


def _manager(project: str):
	if not project or not frappe.db.exists("Construction Project", project):
		raise frappe.DoesNotExistError
	doc = frappe.get_doc("Construction Project", project)
	frappe.has_permission("Construction Project", "manage_clients", doc=doc, throw=True)
	return doc


def _ext(file_name: str) -> str:
	return (file_name or "").rpartition(".")[2].lower()


def _caption(text) -> str:
	text = re.sub(r"[\x00-\x1f\x7f<>\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", str(text or "")).strip()
	return text[:CAPTION]


def _candidates(project: str) -> list[dict]:
	rows = frappe.get_all("File", filters={"cc_project": project, "is_folder": 0, "cc_trashed": ["in", [0, None]],
		"cc_version_of": ["is", "not set"]},  # P3-43 (D-301): a file's earlier versions are not offered
		fields=["name", "file_name", "file_url", "file_size", "cc_client_visible", "modified", "owner", "folder"],
		order_by="modified desc", limit=500)
	theirs = _client_folders(project)
	return [r for r in rows if _ext(r.file_name) in TYPES and cint(r.file_size) <= MAX_SOURCE
		and not is_client(r.owner) and r.folder not in theirs][:200]


def _client_folders(project: str) -> set:
	"""The clients' own folders (06_Client/From client and Discussion files): what lands there came from a client or
	was sent in their conversation, so it never becomes a public sign-in picture (D-275; P3-65: a chat copy of a client's
	photo is the team's File but the client's picture)."""
	from construction_core.workspace import client_folders

	return set(client_folders(project).values()) - {None}


@frappe.whitelist(methods=["GET"])
def project_pictures(project: str) -> dict:
	"""For the project's managers: its marked pictures and the images it can mark."""
	_manager(project)
	pictures = frappe.get_all(DOCTYPE, filters={"project": project},
		fields=["name", "source_file", "caption", "enabled", "marked_on"], order_by="marked_on desc")
	names = {p.source_file for p in pictures}
	files = {f.name: f for f in frappe.get_all("File", filters={"name": ["in", list(names) or [""]]},
		fields=["name", "file_name", "file_url", "cc_trashed"])}
	for p in pictures:
		f = files.get(p.source_file)
		p.file_name = f.file_name if f else ""
		p.url = f.file_url if f else ""  # the project's own file, which its managers read
		p.live = bool(p.enabled and f and not f.cc_trashed)
	candidates = [{"name": c.name, "file_name": c.file_name, "url": c.file_url,
		"client_visible": bool(c.cc_client_visible), "marked": c.name in names} for c in _candidates(project)]
	return {"pictures": pictures, "candidates": candidates, "limit": PER_PROJECT}


def public_copy(content: bytes, ext: str) -> bytes:
	"""The picture a visitor may see, rebuilt from its pixels: decoded only as the format its extension names, its
	size checked before any pixel is decoded, the first frame, turned upright, converted to sRGB, at most MAX_WIDTH
	wide, and written fresh with no metadata at all (no EXIF, XMP, text, comment or colour profile)."""
	from PIL import Image, ImageCms, ImageOps

	fmt = FORMATS[ext]
	with Image.open(BytesIO(content), formats=[fmt]) as source:
		if source.width * source.height > MAX_PIXELS:
			frappe.throw(_("The image is larger than 50 megapixels. Use a smaller copy."))
		icc = source.info.get("icc_profile")
		alpha = source.mode in ("RGBA", "LA", "PA") or "transparency" in source.info
		image = ImageOps.exif_transpose(source)  # a new image of the first frame, upright
		image.load()
	mode = "RGBA" if alpha and fmt != "JPEG" else "RGB"
	if image.mode not in ("RGB", "RGBA", "CMYK"):
		image = image.convert("RGBA" if alpha else "RGB")
	if icc:
		try:
			image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(BytesIO(icc)),
				ImageCms.createProfile("sRGB"), outputMode=mode)
		except Exception:
			image = image.convert(mode)  # an unreadable profile: its pixels as they are, the profile dropped
	if image.mode != mode:
		image = image.convert(mode)
	if image.width > MAX_WIDTH:
		image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.LANCZOS)
	image.info = {}
	out = BytesIO()
	image.save(out, fmt, **({"optimize": True} if fmt == "PNG" else {"quality": 90}))
	return out.getvalue()


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=600)  # each mark decodes a large image
def mark(project: str, file: str, caption: str = "") -> dict:
	"""A manager marks one of the project's own images for the sign-in page (D-272)."""
	_manager(project)
	frappe.db.get_value("Construction Project", project, "name", for_update=True)  # one mark at a time per project
	f = frappe.db.get_value("File", file, ["name", "file_name", "cc_project", "is_folder", "cc_trashed", "owner",
		"cc_version_of", "folder"], as_dict=True)
	if not f or f.cc_project != project or f.is_folder or f.cc_trashed or f.cc_version_of:  # P3-43: not an old version
		frappe.throw(_("Pick an image from this project's files."))
	if is_client(f.owner) or f.folder in _client_folders(project):  # a client's photo (D-158), or chat's copy (P3-65)
		frappe.throw(_("A picture a client sent cannot go on the sign-in page. Use the team's own render."))
	ext = _ext(f.file_name)
	if ext not in FORMATS or ext not in IMAGE_TYPES:
		frappe.throw(_("Pick a JPG, PNG or WebP image."))
	if frappe.db.exists(DOCTYPE, {"source_file": file}):
		frappe.throw(_("This image is already on the sign-in page."))
	if frappe.db.count(DOCTYPE, {"project": project}) >= PER_PROJECT:
		frappe.throw(_("A project can show at most {0} pictures. Remove one first.").format(PER_PROJECT))
	original = frappe.get_doc("File", file).get_content()
	if len(original) > MAX_SOURCE:  # the real bytes, not the size the upload recorded
		frappe.throw(_("The image is larger than 15 MB. Use a smaller copy."))
	try:
		content = public_copy(original, ext)
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.throw(_("This image could not be read."))
	doc = frappe.get_doc({"doctype": DOCTYPE, "project": project, "source_file": file, "caption": _caption(caption),
		"enabled": 1, "marked_by": frappe.session.user, "marked_on": now_datetime()})
	doc.insert(ignore_permissions=True)  # System Manager-only doctype: the manager's right was checked above
	# The public copy belongs to no project, so it never shows in a project's Files. It is Administrator's and attached
	# to the picture (System Manager only), so the manager who marked it cannot edit or repoint it; image() also
	# serves it only while its address and bytes are the ones recorded here.
	copy = get_storage().put(FOLDER, f"signin-{frappe.generate_hash(length=10)}.{ext}", content)
	frappe.db.set_value("File", copy, {"owner": "Administrator", "attached_to_doctype": DOCTYPE,
		"attached_to_name": doc.name}, update_modified=False)
	doc.db_set({"public_file": copy, "public_url": frappe.db.get_value("File", copy, "file_url"),
		"public_hash": hashlib.sha256(content).hexdigest()})
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=600)
def upload_render(project: str) -> dict:
	"""A manager uploads a render for the sign-in page (D-281): one JPG, PNG or WebP (multipart field ``file``) of at
	most 15 MB that decodes as its named format, stored in the project's own files at RENDERS through the storage
	provider, as the manager. It is not marked: marking stays the separate step with its caption (mark)."""
	from PIL import Image

	from construction_core.workspace import root_path

	_manager(project)
	sent = frappe.request.files.get("file") if getattr(frappe, "request", None) else None
	file_name = os.path.basename((sent.filename if sent else "") or "").strip()
	ext = _ext(file_name)
	if not file_name or file_name.startswith(".") or ext not in FORMATS or ext not in IMAGE_TYPES:
		frappe.throw(_("Choose a JPG, PNG or WebP image."))
	content = sent.stream.read(MAX_SOURCE + 1)
	if len(content) > MAX_SOURCE:
		frappe.throw(_("The image is larger than 15 MB. Use a smaller copy."))
	try:
		with Image.open(BytesIO(content), formats=[FORMATS[ext]]) as probe:
			if probe.width * probe.height > MAX_PIXELS:
				frappe.throw(_("The image is larger than 50 megapixels. Use a smaller copy."))
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.throw(_("This image could not be read."))
	name = get_storage().put(f"{root_path(project)}/{RENDERS}", file_name, content, project=project)
	return {"name": name, "file_name": frappe.db.get_value("File", name, "file_name")}


def _picture_for_manager(picture: str):
	if not picture or not frappe.db.exists(DOCTYPE, picture):
		raise frappe.DoesNotExistError
	doc = frappe.get_doc(DOCTYPE, picture)
	_manager(doc.project)
	return doc


@frappe.whitelist(methods=["POST"])
def update(picture: str, caption: str | None = None, enabled: int | str | None = None) -> None:
	doc = _picture_for_manager(picture)
	if caption is not None:
		doc.caption = _caption(caption)
	if enabled is not None:
		doc.enabled = 1 if cint(enabled) else 0
	doc.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def remove(picture: str) -> None:
	_delete(_picture_for_manager(picture))


def _delete(doc) -> None:
	copy = doc.public_file
	frappe.delete_doc(DOCTYPE, doc.name, ignore_permissions=True, force=True)
	if copy and frappe.db.exists("File", copy):
		frappe.delete_doc("File", copy, ignore_permissions=True, force=True)


def on_project_trash(doc, method=None):
	for name in frappe.get_all(DOCTYPE, filters={"project": doc.name}, pluck="name"):
		_delete(frappe.get_doc(DOCTYPE, name))


def on_file_trash(doc, method=None):
	if doc.is_folder:
		return
	for name in frappe.get_all(DOCTYPE, filters={"source_file": doc.name}, pluck="name"):
		_delete(frappe.get_doc(DOCTYPE, name))


def _live(filters=None, limit=SLIDESHOW) -> list[dict]:
	"""Marked pictures whose project exists and whose source is not in the bin, newest first."""
	rows = frappe.db.sql(f"""
		select p.name, p.caption from `tab{DOCTYPE}` p
		join `tabConstruction Project` pr on pr.name = p.project
		join `tabFile` s on s.name = p.source_file and ifnull(s.cc_trashed, 0) = 0
		join `tabFile` c on c.name = p.public_file
		where p.enabled = 1 {"and p.project = %(project)s" if filters else ""}
		order by p.marked_on desc limit {int(limit)}""", filters or {}, as_dict=True)
	return [{"id": r.name, "caption": r.caption or ""} for r in rows]


def for_signin(redirect_to: str | None) -> list[dict]:
	"""The pictures for a sign-in page's boot (D-273): the named project's when it has any, else the slideshow."""
	match = PORTAL_PATH.match(unquote(redirect_to or "")[:200])
	if match:
		own = _live({"project": match.group(1)})
		if own:
			return own
	return _live()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def image(picture: str = ""):
	"""A marked picture's public copy, to anyone (the sign-in page). Checked live on every request; anything else is
	the same 404. Revalidated on every view (no-cache with an ETag), so an unmarked picture stops showing at once."""
	rows = frappe.db.sql(f"""
		select c.name, p.public_url, p.public_hash from `tab{DOCTYPE}` p
		join `tabConstruction Project` pr on pr.name = p.project
		join `tabFile` s on s.name = p.source_file and ifnull(s.cc_trashed, 0) = 0
		join `tabFile` c on c.name = p.public_file and c.file_url = p.public_url and c.is_private = 1
		where p.name = %s and p.enabled = 1 and ifnull(p.public_hash, '') != ''""", (str(picture or "")[:40],))
	if not rows:
		raise frappe.DoesNotExistError
	copy = frappe.get_doc("File", rows[0][0])
	ctype = TYPES.get(_ext(copy.file_name))
	content = copy.get_content() if ctype else b""
	digest = hashlib.sha256(content).hexdigest()
	if not ctype or digest != rows[0][2]:  # the copy is exactly the one mark() made, or nothing
		raise frappe.DoesNotExistError
	etag = '"' + digest[:32] + '"'
	headers = {"ETag": etag, "Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff",
		"Content-Disposition": "inline", "Cross-Origin-Resource-Policy": "same-origin"}
	request = getattr(frappe.local, "request", None)
	if request is not None and request.headers.get("If-None-Match") == etag:
		return Response(status=304, headers=headers)
	return Response(content, status=200, content_type=ctype, headers=headers)
