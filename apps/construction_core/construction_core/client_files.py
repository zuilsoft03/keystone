"""What a client may send, and the virus scan (P3-07; D-159, D-179, D-182, D-183).

``portal_api.send_file`` runs these checks in order before a client's file is stored; ``overrides.file`` scans every
other file a client stores (a profile photo, a private file of their own). Nothing here is whitelisted: the callers
check who asks (DR-5). The scanner is clamd (ClamAV) on the stack's internal ``scan`` network, spoken to over TCP with
its INSTREAM command, standard library only. When it cannot answer, the file is refused: never stored unscanned.
"""

import re
import socket
import struct
import subprocess
import sys
import time
import unicodedata
import zipfile
from contextlib import contextmanager
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import cint, flt, today

CLIENT_TYPES = ("pdf", "jpg", "jpeg", "png", "webp", "docx", "xlsx", "pptx", "dwg", "dxf", "rvt", "ifc")
# P3-75 (D-416, QP-2; D-421): SketchUp files (2021 and later) are checked, but clients may send them only once the check
# has run on two real files (G5); until then the team sends them, and Revit families, in the Team room only.
STAFF_ROOM_TYPES = ("rfa", "skp")
# P3-67 (D-364): voice notes, for clients and staff alike, through the voice upload only (voice_types); the stored
# extension comes from the recording's own bytes (audio.sniff), so it is served with the detected audio type.
AUDIO_TYPES = ("m4a", "ogg", "weba")
MODEL_TYPES = frozenset({"rvt", "rfa", "ifc", "skp"})
MODEL_MAX, OTHER_MAX = 250 * 1024**2, 100 * 1024**2  # D-417: model files up to 250 MB; every other type 100 MB (D-182)
SCAN_IN_REQUEST = 100 * 1024**2  # a larger file is scanned by a background job: about 50 s per 100 MB (P3-07)
BACKGROUND_SCAN_SECONDS = 290.0  # clamd's MaxScanTime is 300 s
MAX_SCAN_SECONDS = 295.0
OLE2 = bytes.fromhex("D0CF11E0A1B11AE1")
SKP_MAGIC = b"\xff\xfe\xff\x0e"
LABEL = {"pdf": "PDF", "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WebP", "docx": "Word", "xlsx": "Excel",
	"pptx": "PowerPoint", "dwg": "DWG", "dxf": "DXF", "rvt": "Revit", "rfa": "Revit family", "ifc": "IFC",
	"skp": "SketchUp", "m4a": "MP4 audio", "ogg": "Ogg audio", "weba": "WebM audio"}
DAILY_BYTES = 1024**3  # per project per day (D-182: files may be as large as the team's, 100 MB)
DAILY_FILES = 50
BURST, BURST_WINDOW = 30, 600  # sends per user per ten minutes: a refused send still costs a scan
STAFF_BURST = 60  # a staff member's chat uploads per ten minutes, with no daily cap (hub §7, P3-65)
MAX_PIXELS = 50_000_000  # providers.storage.MAX_PIXELS: a phone's 48 or 50 megapixel mode
OOXML_MAIN = {
	"docx": ("wordprocessingml.document.main+xml", "word/document.xml"),
	"xlsx": ("spreadsheetml.sheet.main+xml", "xl/workbook.xml"),
	"pptx": ("presentationml.presentation.main+xml", "ppt/presentation.xml"),
}
MAX_ENTRIES, MAX_UNZIPPED, MAX_PART = 5000, 1024**3, 2 * 1024**2
MAX_PDF_OBJECTS = 500_000  # containers walked; measured: 1,500 A0 pages with 45,000 annotations in 1.7 s
CHUNK = 64 * 1024
SCAN_LOG = "construction_core: client file scan"


def types_text() -> str:
	return _("You can send PDF, JPG, PNG, WebP, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), DWG, DXF, Revit (.rvt) "
		"and IFC files.")


def type_limit(ext: str) -> int:
	"""The largest file of this type (D-417): 250 MB for a model file, 100 MB for any other, never above the site's."""
	return min(MODEL_MAX if ext in MODEL_TYPES else OTHER_MAX, client_limit())


LARGE_AT_ONCE, LARGE_TTL = 2, 600  # large files handled at once on the whole site; a crashed one frees after LARGE_TTL


@contextmanager
def large_slot():
	"""At most LARGE_AT_ONCE files above SCAN_IN_REQUEST are handled at once on the site (P3-75 audit: one such upload
	takes about 1.3 GB in a web worker, G7). A token older than LARGE_TTL (a worker killed mid-upload) no longer counts."""
	key = frappe.cache.make_key("cc:large_upload:active")
	token, now = frappe.generate_hash(length=12), time.time()
	frappe.cache.zremrangebyscore(key, "-inf", now - LARGE_TTL)
	frappe.cache.zadd(key, {token: now})
	frappe.cache.expire(key, LARGE_TTL)
	try:
		if frappe.cache.zcard(key) > LARGE_AT_ONCE:
			frappe.throw(_("Other large files are being received just now. Try again in a few minutes."),
				frappe.RateLimitExceededError)
		yield
	finally:
		frappe.cache.zrem(key, token)


@contextmanager
def staff_room_types():
	"""Within the block, check_type also takes the types the team sends in the Team room (STAFF_ROOM_TYPES)."""
	before = getattr(frappe.local, "cc_staff_room_types", False)
	frappe.local.cc_staff_room_types = True
	try:
		yield
	finally:
		frappe.local.cc_staff_room_types = before


@contextmanager
def voice_types():
	"""Within the block, check_type also takes a voice note's types (AUDIO_TYPES): the voice upload only."""
	before = getattr(frappe.local, "cc_voice_types", False)
	frappe.local.cc_voice_types = True
	try:
		yield
	finally:
		frappe.local.cc_voice_types = before


def client_limit() -> int:
	"""The largest file a client may send: the site's upload ceiling, the same as the team's (D-182, D-017)."""
	from frappe.core.api.file import get_max_file_size as request_limit
	from frappe.utils.file_manager import get_max_file_size

	return min(get_max_file_size(), request_limit())


def size_text(limit: int) -> str:
	return f"{limit / 1048576:.1f} MB" if limit >= 1048576 else f"{limit // 1024} KB"


def clean_name(raw: str | None) -> tuple[str, str]:
	"""(display name, extension) of a sent file name. Control, format and bidi characters are dropped (a name cannot
	pretend to end in another type), the path is dropped, and the extension must be plain ASCII."""
	name = unicodedata.normalize("NFC", raw or "")
	name = "".join(c for c in name if unicodedata.category(c) not in ("Cc", "Cf", "Co", "Cs", "Zl", "Zp"))
	name = name.replace("\\", "/").rsplit("/", 1)[-1]
	name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
	base, dot, ext = name.rpartition(".")
	if not dot or not base.strip() or not ext:
		frappe.throw(_("This file has no type.") + " " + types_text())
	if not ext.isascii():
		frappe.throw(_("Files of this type cannot be sent.") + " " + types_text())
	ext = ext.lower()
	display = (re.sub(r'[<>:"/\\|?*%#]', "_", base).strip()[:120] or "file") + "." + ext
	return display, ext


def check_type(ext: str):
	if (ext not in CLIENT_TYPES and not (ext in STAFF_ROOM_TYPES and getattr(frappe.local, "cc_staff_room_types", False))
			and not (ext in AUDIO_TYPES and getattr(frappe.local, "cc_voice_types", False))):
		frappe.throw(_("Files of type .{0} cannot be sent.").format(ext) + " " + types_text())


def _not_valid(ext: str):
	frappe.throw(_("This file is not a valid {0} file").format(LABEL[ext]))


def check_signature(ext: str, content: bytes):
	"""The bytes a type starts with, at offset 0. OOXML is a ZIP: an old Office file (OLE2) or an encrypted one is
	not accepted under a new extension."""
	head = content[:4096]
	ok = {
		"pdf": head.startswith(b"%PDF-"),
		"jpg": head.startswith(b"\xff\xd8\xff"),
		"png": head.startswith(b"\x89PNG\r\n\x1a\n"),
		"webp": head[:4] == b"RIFF" and head[8:12] == b"WEBP",
		"docx": head.startswith(b"PK\x03\x04"),
		"dwg": re.match(rb"AC10\d\d", head[:6]) is not None,
		"dxf": head.startswith(b"AutoCAD Binary DXF\r\n\x1a\x00") or (
			b"\x00" not in head
			and re.match(rb"\s*(999\r?\n[^\r\n]*\r?\n\s*)?0\r?\n\s*SECTION\b", head.removeprefix(b"\xef\xbb\xbf"))
			is not None),
	}
	ok["jpeg"] = ok["jpg"]
	ok["xlsx"] = ok["pptx"] = ok["docx"]
	ok["rvt"] = ok["rfa"] = head.startswith(OLE2)  # an old Word file has the same magic: the structure tells them apart
	ok["ifc"] = head.removeprefix(b"\xef\xbb\xbf").lstrip().startswith(b"ISO-10303-21;")
	ok["skp"] = head.startswith(SKP_MAGIC)
	ok["m4a"] = head[4:8] == b"ftyp"
	ok["ogg"] = head.startswith(b"OggS")
	ok["weba"] = head.startswith(bytes.fromhex("1A45DFA3"))  # EBML
	if not ok[ext]:
		_not_valid(ext)


def check_daily_cap(project: str, size: int, chat: bool = False):
	"""What the project's clients sent today, files and bytes, refused sends not counted. One plain read with no lock
	(a locking read can fail with MariaDB 1020, D-177), so two sends at once may pass it together: a soft cap.
	P3-65: a chat upload counts from its upload, while it waits unsent as much as once it is a File (hub §7: photos
	count as files; the cap is shared by Files and chat). ``chat``: the words for a conversation's composer (L-18)."""
	count, total = sent_today(project)
	if count + 1 > DAILY_FILES or total + size > DAILY_BYTES:
		if chat:
			frappe.throw(_("You can send more files tomorrow. You can still write a message."))
		frappe.throw(_("This project has received all the files it can take from clients today. Try again tomorrow, "
			"or ask the project team."))


def sent_today(project: str) -> tuple[int, int]:
	"""(files, bytes) the project's clients sent today: the cap's one count. P3-71: an upload held for a file request
	counts like one waiting to be sent."""
	count, total = frappe.db.sql(
		"""select count(*), coalesce(sum(size), 0) from (
			select f.file_size as size from `tabFile` f join `tabUser` u on u.name = f.owner
			where f.cc_project = %(p)s and f.is_folder = 0 and u.user_type = 'Website User' and f.creation >= %(d)s
			union all
			select a.file_size from `tabDiscuss Attachment` a join `tabUser` u on u.name = a.uploader
			where a.project = %(p)s and a.state in ('Pending', 'Held') and a.source != 'Link'
				and u.user_type = 'Website User' and a.creation >= %(d)s) sent""",
		{"p": project, "d": today()},
	)[0]
	gone_files, gone_bytes = (cint(frappe.safe_decode(frappe.cache.get(_discarded_key(project, kind)) or b"0"))
		for kind in ("files", "bytes"))
	from construction_core.scan_holds import counted

	held_files, held_bytes = counted(project)  # P3-75: large sends still being checked count from their arrival
	return cint(count) + gone_files + held_files, cint(total) + gone_bytes + held_bytes


def count_discarded(project: str, size: int) -> None:
	"""A client's chat upload taken out unsent still counts for that day (P3-65): it was checked and scanned, and a
	discard must not free the daily cap for the next upload. Kept beside the cap's own read, for two days."""
	for kind, amount in (("files", 1), ("bytes", cint(size))):
		key = _discarded_key(project, kind)
		frappe.cache.incrby(key, amount)
		frappe.cache.expire(key, 2 * 86400)


def _discarded_key(project: str, kind: str) -> str:
	return frappe.cache.make_key(f"cc:client_upload:discarded:{project}:{today()}:{kind}")


def check_burst(user: str, limit: int | None = None, what: str = "upload"):
	"""Shared by send_file, chat uploads and every other file a client stores (overrides.file). The count and its expiry
	are kept together: a counter whose window ran out between two calls starts a new window, never one without an end.
	``limit``: the sender kind's own (STAFF_BURST for the team's chat uploads, P3-65); clients keep BURST. ``what``:
	"link" counts a chat link to a project file (Attach from Files, Ask about this file) apart, with the same limit: it
	costs no scan, so it never takes a scan's place, but nobody makes waiting rows without end."""
	key = frappe.cache.make_key(f"cc:client_upload:burst:{user}" if what == "upload" else f"cc:chat_link:burst:{user}")
	sent = frappe.cache.incrby(key, 1)
	if sent == 1 or frappe.cache.ttl(key) == -1:
		frappe.cache.expire(key, BURST_WINDOW)
	if sent > (BURST if limit is None else limit):
		frappe.throw(_("You have sent many files in a short time. Wait a few minutes and try again."),
			frappe.RateLimitExceededError)


# --- structure (step 7) ----------------------------------------------------------------------------------------


def check_structure(ext: str, content: bytes):
	limit = type_limit(ext)
	if len(content) > limit:  # D-417: only a model file may pass 100 MB
		frappe.throw(_("The file is larger than {0}").format(size_text(limit)))
	if ext in MODEL_TYPES:
		from construction_core import model_files

		return model_files.check(ext, content)
	if ext in OOXML_MAIN:
		_check_ooxml(ext, content)
	elif ext == "pdf":
		_check_pdf(content)
	elif ext in ("jpg", "jpeg", "png", "webp"):
		_check_image(ext, content)
	elif ext in AUDIO_TYPES:  # P3-67: 10 MB, then one sound track, AAC or Opus, at most 300 s (design §3.6)
		from construction_core import audio

		return audio.check(ext, content)  # what the voice note is, for the stage (read once)


def _too_complex():
	frappe.throw(_("This file is too complex to check, so it was not sent."))


def _read_part(z: zipfile.ZipFile, info: zipfile.ZipInfo, ext: str) -> bytes:
	if info.file_size > MAX_PART:
		_too_complex()
	with z.open(info) as fh:
		data = fh.read(MAX_PART + 1)
	if len(data) > MAX_PART:
		_too_complex()
	if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
		_not_valid(ext)
	return data


def _check_zip_directory(ext: str, content: bytes):
	"""Read the ZIP's end record before zipfile builds an object for every entry: too many entries, or a directory too
	large for them, is refused first (a directory of millions of tiny entries costs gigabytes to open)."""
	at = content.rfind(b"PK\x05\x06", max(0, len(content) - 65557))
	if at < 0 or len(content) < at + 22:
		_not_valid(ext)
	entries, size = struct.unpack("<H", content[at + 10:at + 12])[0], struct.unpack("<I", content[at + 12:at + 16])[0]
	if entries == 0xFFFF or size == 0xFFFFFFFF or entries > MAX_ENTRIES or size > MAX_ENTRIES * (46 + 1024):
		_too_complex()


def _check_ooxml(ext: str, content: bytes):
	"""An Office file is a ZIP of XML parts. No macros, ActiveX or embedded programs, no template or frame loaded from
	outside the file, no password; read without unpacking it (the parts read are small and bounded)."""
	label = LABEL[ext]
	_check_zip_directory(ext, content)
	try:
		z = zipfile.ZipFile(BytesIO(content))
	except (zipfile.BadZipFile, ValueError, OSError):
		_not_valid(ext)
	with z:
		infos = z.infolist()
		if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNZIPPED:
			_too_complex()
		names = {i.filename: i for i in infos}
		for i in infos:
			if i.flag_bits & 0x1:
				frappe.throw(_("Password-protected files cannot be sent."))
			if i.filename.startswith(("/", "\\")) or ".." in i.filename.replace("\\", "/").split("/"):
				_not_valid(ext)
		types = names.get("[Content_Types].xml")
		if not types:
			_not_valid(ext)
		declared = _read_part(z, types, ext).decode("utf-8", "replace")
		main_type, main_part = OOXML_MAIN[ext]
		if main_type not in declared or main_part not in names:
			frappe.throw(_("This file is not a valid {0} file").format(label))
		macros = _("Files with macros or embedded programs cannot be sent. Save a copy as a plain .{0} file and send "
			"that.").format(ext)
		if any(word in declared for word in ("macroEnabled", "vbaProject", "activeX", "oleObject")):
			frappe.throw(macros)
		for name in names:
			low = name.lower()
			if (low.endswith(("vbaproject.bin", "vbadata.xml")) or "/activex/" in low
					or ("/embeddings/" in low and low.rsplit("/", 1)[-1].startswith("oleobject"))):
				frappe.throw(macros)
		rels = [i for i in infos if i.filename.endswith(".rels")]
		if len(rels) > 2000:
			_too_complex()
		external = re.compile(
			rb'<Relationship\b(?=[^>]*TargetMode="External")(?=[^>]*Type="[^"]*/(attachedTemplate|oleObject|frame|subDocument)")',
			re.I)
		for info in rels:
			if external.search(_read_part(z, info, ext)):
				frappe.throw(_("This document loads content from outside the file, which we do not accept. Save a "
					"copy without external links and send that."))


# The PDF walk runs in a child process (P3-07 review, C1): a PDF of a few KB can hold object streams that inflate to
# tens of millions of objects inside one parse, which no counter in the walk can stop. The child sets hard limits on its
# own CPU time and memory before it reads anything (never through preexec_fn, which can deadlock a threaded server
# between fork and exec); when it hits one, the file is "too complex". It imports pypdf only, never frappe.
PDF_CPU_SECONDS, PDF_MEMORY = 10, 768 * 1024**2
PDF_WALK = r"""
import resource
import sys
LIMIT, CPU, MEMORY = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
resource.setrlimit(resource.RLIMIT_CPU, (CPU, CPU))
resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
from io import BytesIO
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
try:
	reader = PdfReader(BytesIO(sys.stdin.buffer.read()), strict=False)
	if reader.is_encrypted and not reader.decrypt(""):
		sys.exit(11)
	stack, seen, count = [reader.trailer.get("/Root")], set(), 0
	while stack:
		obj = stack.pop()
		if isinstance(obj, IndirectObject):
			ref = (obj.idnum, obj.generation)
			if ref in seen:
				continue
			seen.add(ref)
			obj = obj.get_object()
		count += 1
		if count > LIMIT:
			sys.exit(13)
		if isinstance(obj, DictionaryObject):
			for key, value in obj.items():
				if key in ("/JS", "/JavaScript", "/XFA", "/RichMedia"):
					sys.exit(10)
				if key == "/S" and value in ("/JavaScript", "/Launch", "/RichMediaExecute"):
					sys.exit(10)
				if isinstance(value, (DictionaryObject, ArrayObject, IndirectObject)):  # numbers and names hold nothing
					stack.append(value)
		elif isinstance(obj, ArrayObject):
			stack.extend(v for v in obj if isinstance(v, (DictionaryObject, ArrayObject, IndirectObject)))
except MemoryError:
	sys.exit(13)
except Exception:
	sys.exit(12)
sys.exit(0)
"""


def _check_pdf(content: bytes):
	"""No JavaScript, launch actions, XFA forms or rich media anywhere in the document, references resolved; read in
	a child process with hard limits on time and memory."""
	try:
		done = subprocess.run([sys.executable, "-I", "-c", PDF_WALK, str(MAX_PDF_OBJECTS), str(PDF_CPU_SECONDS),
			str(PDF_MEMORY)], input=content, capture_output=True, timeout=PDF_CPU_SECONDS * 3, check=False)
	except subprocess.TimeoutExpired:
		_too_complex()
	code = done.returncode
	if code == 0:
		return
	if code == 10:
		frappe.throw(_("This PDF contains scripts or interactive content, which we do not accept. Print it to a new "
			"PDF and send that."))
	if code == 11:
		frappe.throw(_("Password-protected files cannot be sent."))
	if code == 12:
		frappe.throw(_("This PDF could not be read."))
	_too_complex()  # 13, or killed by a limit (a negative code)


def _check_image(ext: str, content: bytes):
	"""The header only: the format must be the extension's, at most 50 megapixels, one frame. Nothing is decoded."""
	from PIL import Image

	fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}[ext]
	try:
		with Image.open(BytesIO(content)) as im:
			if im.format != fmt:
				_not_valid(ext)
			if im.width * im.height > MAX_PIXELS:
				frappe.throw(_("The image is larger than 50 megapixels. Send a smaller copy."))
			if getattr(im, "n_frames", 1) != 1:
				frappe.throw(_("Animated images cannot be sent. Send a still image."))
	except frappe.ValidationError:
		raise
	except Image.DecompressionBombError:
		frappe.throw(_("The image is larger than 50 megapixels. Send a smaller copy."))
	except Exception:
		_not_valid(ext)


# --- the virus scan (step 8) -----------------------------------------------------------------------------------


class ScanUnavailable(frappe.ValidationError):
	http_status_code = 503


class ScanThreat(frappe.ValidationError):
	"""clamd found a threat (P3-75: a held file's reason, by class, never by its words)."""


class ScanIncomplete(frappe.ValidationError):
	"""clamd could not check the file fully: a limit, or encryption."""


def _log(result: str, project: str | None = None):
	frappe.log_error(title=SCAN_LOG, message=f"user={frappe.session.user} project={project or '-'} result={result}",
		defer_insert=True)  # never the bytes


def scan(content: bytes, *, project: str | None = None, sent: bool = True, budget: float | None = None):
	"""Send the bytes to clamd and refuse the file unless it answers exactly ``stream: OK``. An infection is refused,
	so is a file clamd could not check fully (a limit or encryption), and any other answer, a timeout or no answer
	refuses the file as "try again later" (ScanUnavailable, HTTP 503). ``sent``: the client sent the file (portal), or
	stored it (a profile photo, a file of their own)."""
	host = frappe.conf.get("cc_clamd_host") or "clamav"
	port = cint(frappe.conf.get("cc_clamd_port")) or 3310
	# A caller passes what it may wait: what is left of its request's 120 s (P3-07 audit S2), or a background job's
	# BACKGROUND_SCAN_SECONDS (P3-75), never more than clamd's own MaxScanTime; cc_clamd_timeout caps it (tests).
	budget = 95.0 if budget is None else min(budget, MAX_SCAN_SECONDS)
	if flt(frappe.conf.get("cc_clamd_timeout")):
		budget = min(budget, flt(frappe.conf.get("cc_clamd_timeout")))
	deadline = time.monotonic() + budget
	not_now = (_("Files cannot be checked for viruses just now, so this file was not sent. Please try again later.")
		if sent else _("Files cannot be checked for viruses just now, so this file was not saved. Please try again later."))
	reply = b""
	try:
		with socket.create_connection((host, port), timeout=min(5.0, budget)) as s:

			def left():
				remaining = deadline - time.monotonic()
				if remaining <= 0:
					raise TimeoutError
				s.settimeout(remaining)

			left()
			s.sendall(b"zINSTREAM\x00")
			for i in range(0, len(content), CHUNK):
				part = content[i:i + CHUNK]
				left()
				s.sendall(struct.pack("!I", len(part)) + part)
			left()
			s.sendall(struct.pack("!I", 0))
			while not reply.endswith(b"\x00") and len(reply) < 4096:
				left()
				got = s.recv(4096)
				if not got:
					break
				reply += got
	except OSError as e:  # refused, unknown host, reset, broken pipe, a timeout (TimeoutError is an OSError)
		_log(f"unavailable ({type(e).__name__})", project)
		raise ScanUnavailable(not_now) from None
	verdict = reply.rstrip(b"\x00").decode("utf-8", "replace").strip()
	if verdict == "stream: OK":
		return
	if verdict.startswith("stream: ") and verdict.endswith(" FOUND"):
		signature = verdict[len("stream: "):-len(" FOUND")]
		_log(f"found {signature}", project)
		if signature.startswith(("Heuristics.Limits.Exceeded", "Heuristics.Encrypted")):
			frappe.throw(_("This file could not be checked for viruses, so it was not sent.") if sent
				else _("This file could not be checked for viruses, so it was not saved."), ScanIncomplete)
		frappe.throw(_("The virus scan found a threat in this file, so it was not sent.") if sent
			else _("The virus scan found a threat in this file, so it was not saved."), ScanThreat)
	_log(f"unavailable ({verdict[:120] or 'no answer'})", project)
	raise ScanUnavailable(not_now)
