"""File versions (P3-43, D-301, D-302, D-303).

A file keeps its id and name through every revision. The content it had is kept as a version File beside it,
named ``base (vYYYYmmdd-HHMMSS).ext``, which points back at it (``cc_version_of``), holds the revision's letter,
author, time and note, and is never shown to clients (permissions.can_access, permissions.guard_version_fields).
Version rows leave every list.

Where the content goes (D-305, amending D-301):
- An upload or a restore never writes in place. The version row takes the address the file had (or, when another
  file of a project shares that address, a copy of its own, and the address stays with them), and the new content
  goes to a path of its own. So whatever points at the old address (a drawing, Frappe's attachment rows, a link)
  keeps the content it was made on, and clients fetch the new content at a new address.
- An Office save writes in place (P1-17, D-101: links by address follow the edited file; test_office pins it),
  unless another File shares the address; the version row gets a copy of the old bytes.

Letters: the first content is A; each new revision takes the next letter (Z is followed by AA). The letters are
stored, and the next one follows the highest already used, so deleting a version row never makes a letter repeat
(P3-43 audit S1). One revision at a time: the file's row is locked first. A second one at the same moment fails with
MariaDB 1020 (snapshot isolation) and is tried once more by the endpoint (files.api.upload_version, restore).

A file's history is deleted only with the file, by a System Manager (permissions.can_access refuses anyone else's
delete of a version row or of a file that has them; ``on_file_trash`` deletes the version rows with their file).

A drawing measured in Takeoff follows the owner's choice (D-302): ``reuse`` moves it onto the new content (its
geometry read again, its points and scale kept); ``copy`` leaves it and its takeoffs on the old revision and copies
them onto the new one; ``new`` leaves them on the old revision only. A drawing with no takeoff follows the file when
the new content can be read for it, else it stays on its revision. Drawings are asked about only when no other file
of the project shares the address: one made on that other file is not this file's to move.
"""

import os
import re

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import escape_html, get_fullname, now_datetime

from construction_core.core.events import emit
from construction_core.permissions import is_client
from construction_core.providers.storage import CLIENT_FOLDERS, own_path, write_atomic

NOTE_MAX = 280
NOTE_STRIP = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u00ad\u061c\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")  # control, invisible and direction marks
TAKEOFF_CHOICES = ("reuse", "copy", "new")
DRAWING_EXTENSIONS = ("dxf", "pdf")
REV_SUFFIX = re.compile(r"\s*\(Rev [A-Z]{1,3}\)$")


def letter(n: int) -> str:
	"""The n-th revision's letter, as spreadsheet columns: 1 A, 26 Z, 27 AA, 52 AZ, 53 BA."""
	n, out = max(int(n), 1), ""
	while n:
		n, r = divmod(n - 1, 26)
		out = chr(65 + r) + out
	return out


def clean_note(note: str | None) -> str:
	note = " ".join(NOTE_STRIP.sub("", note or "").split())
	if len(note) > NOTE_MAX:
		frappe.throw(_("Keep the note to {0} characters").format(NOTE_MAX))
	return note


def split_name(file_name: str) -> tuple[str, str]:
	base, dot, ext = (file_name or "").rpartition(".")
	return (base, f".{ext}") if dot and base else (file_name, "")


def read_bytes(f) -> bytes:
	"""A File's stored bytes, as stored (``File.get_content`` decodes text, which changes a DXF or a CSV)."""
	with open(f.get_full_path(), "rb") as fh:
		return fh.read()


def number(rev: str | None) -> int:
	"""The inverse of ``letter``: A 1, Z 26, AA 27. Anything else is 0."""
	rev = (rev or "").strip().upper()
	if not rev.isalpha() or not rev.isascii():
		return 0
	n = 0
	for c in rev:
		n = n * 26 + ord(c) - 64
	return n


def count(file: str) -> int:
	return frappe.db.count("File", {"cc_version_of": file})


def _numbers(f) -> tuple[int, int]:
	"""The file's current revision number and the highest number its version rows hold."""
	held = max((number(r) for r in frappe.get_all("File", filters={"cc_version_of": f.name}, pluck="cc_rev")), default=0)
	return max(number(f.cc_rev) or 1, held + 1), held


def current_rev(file: str) -> str:
	return letter(_numbers(frappe.get_doc("File", file))[0])


def on_file_trash(doc, method=None):
	"""File.on_trash: a working file is deleted with its history (only a System Manager may delete it, see
	permissions.can_access); the version rows' bytes go with them unless another File still uses them."""
	if doc.get("cc_version_of") or doc.is_folder:
		return
	for name in frappe.get_all("File", filters={"cc_version_of": doc.name}, pluck="name"):
		frappe.delete_doc("File", name, ignore_permissions=True)  # the file's own delete was permission-checked


def is_version(file: str) -> bool:
	return bool(frappe.db.get_value("File", file, "cc_version_of"))


# --- checks -------------------------------------------------------------------------------------------------------


def editing(f) -> bool:
	"""Whether the file is open in Office now, or an editor is opening it: a new revision under it would be
	overwritten by the editor's copy."""
	from construction_core.office.api import _sessions, opening

	key = frappe.db.get_value("File", f.name, "cc_office_key")
	return bool(key and key in _sessions()) or opening(f.name)


def check_revisable(f):
	"""The rules a new revision or a restore must pass (D-301). The caller checked the session user is staff."""
	from construction_core.office.api import _locked

	if f.is_folder or not f.cc_project or f.cc_trashed or f.cc_version_of:
		raise frappe.DoesNotExistError(_("File not found"))
	if not frappe.has_permission("File", "write", doc=f):
		frappe.throw(_("You cannot change this file"), frappe.PermissionError)
	if is_client(f.owner) or _folder_path_of(f) in CLIENT_FOLDERS:
		frappe.throw(_("A file a client sent stays as they sent it"), frappe.PermissionError)
	from construction_core.discuss import media  # here: discuss imports files

	media.refuse_chat_made(f.name)  # P3-67 audit S3: the Team room's chat files too (a voice note's bytes were checked)
	if _locked(f):
		frappe.throw(_("This file is a document under review or published: issue a new revision of the document instead"))
	if editing(f):
		frappe.throw(_("Someone is editing this file in Office. Try again when they have closed it."))


def _folder_path_of(f) -> str:
	from construction_core.files.api import _folders

	where = {fid: path for path, fid in _folders(f.cc_project).items()}
	return where.get(f.folder, "")


def same_type(f, file_name: str):
	if split_name(file_name)[1].lower() != split_name(f.file_name)[1].lower():
		frappe.throw(_("A new version keeps the file's type: choose a {0} file").format(
			split_name(f.file_name)[1].lstrip(".").upper() or _("file of the same type")))


def check_size(f, content: bytes) -> None:
	"""D-417 (P3-75): a model file may be 250 MB; every other type stays at 100 MB, whatever the site's ceiling."""
	from construction_core.client_files import size_text, type_limit

	limit = type_limit(split_name(f.file_name)[1].lstrip(".").lower())
	if len(content) > limit:
		frappe.throw(_("The file is larger than {0}").format(size_text(limit)))


def checked_content(f, content: bytes) -> bytes:
	"""What a staff upload gets from Frappe (P2-04): its size limit, its JPEG EXIF strip when the site turns it on,
	and its refusal of a PDF with scripts."""
	from frappe.utils.image import strip_exif_data
	from frappe.utils.pdf import pdf_contains_js

	ext = split_name(f.file_name)[1].lower()
	if ext in (".jpg", ".jpeg") and frappe.get_system_settings("strip_exif_metadata_from_uploaded_images"):
		content = strip_exif_data(content, "image/jpeg")
	check_size(f, content)
	if ext == ".pdf":
		try:
			scripted = pdf_contains_js(content)
		except Exception:
			frappe.throw(_("This PDF could not be read."))
		if scripted:
			frappe.throw(_("This PDF cannot be uploaded as it contains unsafe content."))
	return content


# --- drawings measured in Takeoff ------------------------------------------------------------------------------


def _sharers(f) -> list:
	"""The other files of a project on this file's address (Frappe stores identical content once): not its version
	rows, and not the rows Frappe attaches to a drawing."""
	return frappe.get_all("File", filters={"file_url": f.file_url, "name": ["!=", f.name], "is_folder": 0,
		"cc_project": ["is", "set"], "cc_version_of": ["is", "not set"]}, pluck="name")


def drawings(f) -> list[dict]:
	"""The Takeoff drawings made on the file's current content, each with its number of takeoffs. None when another
	file of a project shares the address: a drawing on it may have been made on that file (P3-43 review)."""
	if split_name(f.file_name)[1].lower().lstrip(".") not in DRAWING_EXTENSIONS or _sharers(f):
		return []
	rows = frappe.get_all("CAD Drawing", filters={"file": f.file_url, "project": f.cc_project},
		fields=["name", "title"], order_by="creation asc")
	for r in rows:
		r["takeoffs"] = frappe.db.count("Takeoff", {"drawing": r.name})
	return rows


def _titled(title: str, rev: str) -> str:
	suffix = f" (Rev {rev})"
	return f"{REV_SUFFIX.sub('', title or _('Drawing'))[:140 - len(suffix)].rstrip()}{suffix}"


def _stay(d, version):
	"""The drawing stays on the revision it was measured on, which the version row now holds. A drawing's file is
	set once for users (its takeoffs are measured on it); only its title says the revision, and its address follows
	the content if the version row holds a copy of its own, so the system writes it after checking the user may
	change the drawing."""
	d.check_permission("write")
	changes = {"title": _titled(d.title, version.cc_rev)}
	if d.file != version.file_url:
		changes["file"] = version.file_url
	d.db_set(changes)


def _copy_onto(d, f, rev: str) -> str:
	"""A copy of the drawing and its takeoffs on the file's new content, for the team to adjust (D-302)."""
	copy = frappe.get_doc({"doctype": "CAD Drawing", "project": d.project, "title": _titled(d.title, rev),
		"file": f.file_url, "source": d.source, "page": d.page, "calibrated": d.calibrated, "unit_to_m": d.unit_to_m})
	copy.insert()
	for t in frappe.get_all("Takeoff", filters={"drawing": d.name}, pluck="name", order_by="creation asc"):
		src = frappe.get_doc("Takeoff", t)
		frappe.get_doc({"doctype": "Takeoff", "drawing": copy.name, "project": src.project, "title": src.title,
			"kind": src.kind, "unit": src.unit, "color": src.color,
			"items": [{"label": i.label, "quantity": i.quantity, "points": i.points} for i in src.items]}).insert()
	return copy.name


def _follow(d, f):
	"""The drawing follows the file's new content (the owner's choice, D-302): its geometry is read again; its
	points and its scale stay (P3-43 review: an uncalibrated drawing would take the new file's units under points
	measured in the old ones). The new address holds only the file itself when CAD Drawing reads it (it takes the
	newest File on the address), and Frappe adds its own attachment row for the drawing on the save; the old one
	stays on the old address with the old content."""
	d.check_permission("write")
	scale = d.unit_to_m
	d.db_set("file", f.file_url)
	d.geometry = None
	d.save()
	if d.unit_to_m != scale:
		d.db_set("unit_to_m", scale, update_modified=False)


def _follow_or_stay(d, f, version):
	"""A drawing with no takeoff follows the file when its new content can be read for it (a PDF page may be gone),
	else it stays on its revision."""
	frappe.db.savepoint("cc_follow")
	try:
		_follow(d, f)
	except frappe.ValidationError:
		frappe.db.rollback(save_point="cc_follow")
		frappe.clear_last_message()
		_stay(frappe.get_doc("CAD Drawing", d.name), version)


# --- a new revision ---------------------------------------------------------------------------------------------


def revise(file: str, content: bytes, *, note: str = "", comment: str = "", who: str | None = None,
		by: str | None = None, takeoffs: str | None = None, check: bool = True, in_place: bool = False) -> dict:
	"""Make ``content`` the file's next revision; keep its current content as a version row. ``comment`` is the
	file's Activity line, a translated template with ``{rev}``, ``{old}``, ``{note}`` and ``{who}`` (the session
	user's name unless given); ``by`` is who made the revision (the session user unless given). ``in_place`` is the
	Office save's way (D-305). Returns the new letter, the version row and the copies of drawings made for D-302's
	``copy``; content the same as the current is no new revision."""
	frappe.db.get_value("File", file, "name", for_update=True)  # one revision at a time, then read it afresh
	f = frappe.get_doc("File", file)
	check_size(f, content)  # every path: a new version, a restore, an Office save (P3-75, D-417)
	if check:
		check_revisable(f)
	else:
		from construction_core.discuss import media

		media.refuse_chat_made(f.name)  # an Office save in place: a chat file is never rewritten (P3-67 audit S3)
	note = clean_note(note)
	cur, _held = _numbers(f)
	old_url, old = f.file_url, read_bytes(f)
	if content == old:  # P3-43 review: an Office close after a save of the same bytes, or a restore of the same
		if check:
			frappe.throw(_("This is the same content as the current Rev {0}").format(letter(cur)))
		return {"rev": letter(cur), "version": None, "drawings": []}
	on = [] if in_place else drawings(f)
	if any(d.takeoffs for d in on) and takeoffs not in TAKEOFF_CHOICES:
		frappe.throw(_("Choose what happens to the takeoff of this drawing"))
	stamp = now_datetime().strftime("%Y%m%d-%H%M%S")
	base, ext = split_name(f.file_name)
	if in_place:
		version = _archive(f, old, stamp, letter(cur))
		if frappe.db.count("File", {"file_url": old_url}) == 1:
			path = f.get_full_path()
			write_atomic(path, content)
			frappe.db.after_rollback.add(lambda: os.path.exists(path) and write_atomic(path, old))
			url = old_url
		else:
			url = own_path(base, ext, content)  # the path is shared: never write another File's bytes
	else:
		version = _archive(f, old, stamp, letter(cur), take=not _sharers(f))
		url = own_path(base, ext, content)
		_renew_office_key(f)
	rev, user, at = letter(cur + 1), frappe.session.user, now_datetime()
	f.db_set({"file_url": url, "content_hash": get_content_hash(content), "file_size": len(content), "cc_rev": rev,
		"cc_rev_by": by or user, "cc_rev_on": at, "cc_rev_note": note})
	from construction_core.approvals import canonical, subjects  # here: approvals imports this module

	subjects.on_file_revised(f.cc_project, canonical.sha256(old))  # P3-77 (§3.10): requests that froze the old bytes
	# P3-69 (§3.9): a design event after the commit. Keyed by the revision's time, not its letter: a retry after a lost
	# race (1020) takes the same letter, and the first attempt's key would hold its event back.
	emit("file.revised", doctype="File", name=f.name, version=str(at))
	copies = []
	for d in on:  # each is on the old address, which now holds the old content
		doc = frappe.get_doc("CAD Drawing", d.name)
		if not d.takeoffs:
			_follow_or_stay(doc, f, version)
		elif takeoffs == "reuse":
			_follow(doc, f)
		else:
			_stay(doc, version)
			if takeoffs == "copy":
				copies.append(_copy_onto(doc, f, rev))
	if comment:
		who = get_fullname(by or user) if who is None else who
		f.add_comment("Info", escape_html(comment.format(rev=rev, note=note, old=version.cc_rev, who=who)))
	return {"rev": rev, "version": version.name, "drawings": copies}


def _renew_office_key(f):
	"""New content, so a new Office document key: the Document Server caches a document by its key for a day, and
	an editor opened later on the old key would get the old content and save it over the new (P3-43 review). No
	editor is open (check_revisable)."""
	from construction_core.office.api import _rotate_key

	if frappe.db.get_value("File", f.name, "cc_office_key"):
		_rotate_key(f)


def version_name(file_name: str, stamp: str) -> str:
	"""``base (vYYYYmmdd-HHMMSS).ext`` within File's 140 characters."""
	base, ext = split_name(file_name)
	suffix = f" (v{stamp}){ext}"
	return f"{base[:140 - len(suffix)].rstrip()}{suffix}"


def _archive(f, content: bytes, stamp: str, rev: str, take: bool = False):
	"""The file's current content as a version row, beside it, attached like it so the team reads it, never client
	visible, with the revision's author, time and note (a file never revised: its owner and creation). With ``take``
	it takes the file's address (D-305); otherwise, or when Frappe will not let this user reuse that address, it gets
	a copy of its own."""
	base, ext = split_name(f.file_name)
	attached = ({"attached_to_doctype": f.attached_to_doctype, "attached_to_name": f.attached_to_name}
		if f.attached_to_doctype and f.attached_to_name
		else {"attached_to_doctype": "Construction Project", "attached_to_name": f.cc_project})
	row = {"doctype": "File", "file_name": version_name(f.file_name, stamp), "is_private": 1, "folder": f.folder,
		"cc_project": f.cc_project, "cc_client_visible": 0, "content_hash": get_content_hash(content),
		"file_size": len(content), **attached, "cc_version_of": f.name, "cc_rev": rev,
		"cc_rev_by": f.cc_rev_by or f.owner, "cc_rev_on": f.cc_rev_on or f.creation, "cc_rev_note": f.cc_rev_note or ""}
	v = None
	if take:
		try:
			v = _insert_version({**row, "file_url": f.file_url})
		except frappe.PermissionError:  # Frappe's own check of who may reuse a private address (another's row)
			frappe.clear_last_message()
	if v is None:
		v = _insert_version({**row, "file_url": own_path(f"{base}-v{stamp}", ext, content)})
	if v.file_size != len(content):  # File.validate takes a file_size sent with the request over the real one
		v.db_set("file_size", len(content), update_modified=False)
	return v


def _insert_version(row: dict):
	v = frappe.get_doc(row)
	v.flags.copy_from_existing_file = True  # the address is given: Frappe must not point it at an identical file
	v.flags.cc_system = True  # permissions.guard_version_fields
	# ignore_permissions: the caller checked the user may change the file (check_revisable, or Office's callback).
	return v.insert(ignore_permissions=True)


def history(f) -> list[dict]:
	"""Every revision of a file, newest first: the current content, then its version rows."""
	rows = frappe.get_all("File", filters={"cc_version_of": f.name},
		fields=["name", "cc_rev", "cc_rev_by", "cc_rev_on", "cc_rev_note", "file_size", "file_url", "content_hash",
			"creation"], order_by="creation desc")
	names = {}

	def who(user):
		if user not in names:
			names[user] = get_fullname(user) if user else ""
		return names[user]

	cur_by = f.cc_rev_by or f.owner
	out = [{"rev": letter(_numbers(f)[0]), "current": True, "version": None, "who": who(cur_by),
		"when": f.cc_rev_on or f.creation, "note": f.cc_rev_note or "", "file_size": f.file_size,
		"url": f.file_url, "content_hash": f.content_hash or ""}]
	for r in rows:
		out.append({"rev": r.cc_rev, "current": False, "version": r.name, "who": who(r.cc_rev_by),
			"when": r.cc_rev_on or r.creation, "note": r.cc_rev_note or "", "file_size": r.file_size,
			"url": r.file_url, "content_hash": r.content_hash or ""})
	return out
