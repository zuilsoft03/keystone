"""PDF pages as takeoff drawings (P1-18, D-099).

The browser draws the page with PDF.js as the background of the shared takeoff engine; the server only needs the
page's size, so it reads the page box and rotation and nothing else (no content stream is parsed here). Drawing
units are PDF points with y up, as PDF.js shows the page: the visible (crop) box, rotated by the page's /Rotate. A
PDF's paper scale is not the drawing's scale, so a PDF drawing is measured after calibration on a known distance.
"""

import io
import math

MAX_BYTES = 60 * 1024 * 1024
MAX_SIDE = 14_400  # points: the PDF limit of 200 inches
MIN_SIDE = 1


class PDFError(ValueError):
	pass


def page_geometry(content: bytes, page: int) -> dict:
	"""Geometry for the takeoff engine: no vector items, the page extents and the page facts."""
	from pypdf import PdfReader
	from pypdf.errors import PyPdfError

	if isinstance(content, str):
		content = content.encode("latin-1", "replace")
	if len(content) > MAX_BYTES:
		raise PDFError(f"the PDF is larger than {MAX_BYTES // (1024 * 1024)} MB")
	try:
		reader = PdfReader(io.BytesIO(content), strict=False)
		if reader.is_encrypted:
			raise PDFError("the PDF is password-protected: save an unprotected copy")
		pages = len(reader.pages)
		if not 1 <= page <= pages:
			raise PDFError(f"the PDF has {pages} page(s); pick a page from 1 to {pages}")
		p = reader.pages[page - 1]
		box = p.cropbox
		width, height = abs(float(box.width)), abs(float(box.height))
		rotation = int(p.get("/Rotate", 0) or 0) % 360
	except PDFError:
		raise
	except (PyPdfError, ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as e:
		raise PDFError("the file is not a readable PDF") from e
	if rotation not in (0, 90, 180, 270):
		raise PDFError("the page has an invalid rotation")
	if rotation in (90, 270):
		width, height = height, width
	for side in (width, height):
		if not (math.isfinite(side) and MIN_SIDE <= side <= MAX_SIDE):
			raise PDFError("the page size is not a valid drawing size")
	width, height = _clean(width), _clean(height)
	return {"units": "pt", "unit_to_m": None, "layers": [], "extents": [0, 0, width, height], "count": 0,
		"items": [], "pdf": {"page": page, "pages": pages, "width": width, "height": height}}


def _clean(v: float):
	return int(v) if float(v).is_integer() else round(v, 4)
