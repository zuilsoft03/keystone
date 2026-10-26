"""Which reader draws which bytes. The kind is chosen by magic bytes, never by the name (design §15.1: one local
``.dxf`` is really a DWG); the name's type only decides among formats that share a container (an OLE2 file is a
Revit file only when it is named so)."""

import re

from construction_core.previews.readers.common import NOT_SUPPORTED, Refused

PDF, IMAGE, DWG, DXF, RVT, IFC, SKP, OFFICE = "pdf", "image", "dwg", "dxf", "rvt", "ifc", "skp", "office"
PAGE = "page"  # a converter's PNG of a page (the Document Server's), drawn again in the renderer
RENDERED = (PDF, IMAGE, PAGE, DWG, DXF, RVT, IFC)  # drawn (or read, for IFC) in the renderer
OFFICE_TYPES = ("docx", "xlsx", "pptx", "doc", "xls", "ppt")
OLE2 = bytes.fromhex("D0CF11E0A1B11AE1")
DXF_TEXT = re.compile(rb"\s*(999\r?\n[^\r\n]*\r?\n\s*)?0\r?\n\s*SECTION\b")


def sniff(head: bytes, ext: str) -> str | None:
	"""The kind of a file from its first 4 KB, or None when no preview can be made of it."""
	ext = (ext or "").lower()
	if head.startswith(b"%PDF-"):
		return PDF
	if head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
		return IMAGE
	if re.match(rb"AC10\d\d", head[:6]):
		return DWG
	if head.startswith(OLE2):  # a Revit file, an old Office file, or a password-protected new one (an OLE wrapper)
		return RVT if ext in ("rvt", "rfa") else OFFICE if ext in OFFICE_TYPES else None
	if head.startswith(b"PK\x03\x04"):
		return OFFICE if ext in ("docx", "xlsx", "pptx") else None
	if head.startswith(b"\xff\xfe\xff\x0e"):
		return SKP if ext == "skp" else None
	body = head.removeprefix(b"\xef\xbb\xbf")
	if body.lstrip().startswith(b"ISO-10303-21;"):
		return IFC if ext == "ifc" else None
	if b"\x00" not in head and DXF_TEXT.match(body):
		return DXF
	return None


def render(kind: str, fh, px: int):
	"""The kind's reader; imported only when used, so a job loads one parser."""
	if kind == PAGE:
		from construction_core.previews.readers import image

		return image.render_page(fh, px)
	if kind == IMAGE:
		from construction_core.previews.readers import image as reader
	elif kind == PDF:
		from construction_core.previews.readers import pdf as reader
	elif kind == DWG:
		from construction_core.previews.readers import dwg as reader
	elif kind == DXF:
		from construction_core.previews.readers import dxf_draw as reader
	elif kind == RVT:
		from construction_core.previews.readers import rvt as reader
	elif kind == IFC:
		from construction_core.previews.readers import ifc as reader
	else:
		raise Refused(NOT_SUPPORTED)
	return reader.render(fh, px)
