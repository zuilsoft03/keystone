"""PDF page 1 by PDFium (pypdfium2; design §15.2): drawn into a fixed pixel box whatever the page's size, forms off,
one process per job (PDFium is not thread-safe). A file that needs a password gets the lock badge and no preview;
one encrypted with an empty password is drawn, and says so in ``meta``."""

from construction_core.previews.readers.common import FAILED, LOCKED, Refused, to_webp

MAX_SCALE = 8.0  # a postage-stamp page is not drawn larger than 8x (576 dpi)


def render(fh, px: int):
	import pypdfium2 as pdfium
	import pypdfium2.raw as raw

	box = px * 2
	try:
		pdf = pdfium.PdfDocument(fh)
	except pdfium.PdfiumError as e:
		raise Refused(LOCKED if "password" in str(e).lower() else FAILED) from None
	try:
		if len(pdf) < 1:
			raise Refused(FAILED)
		encrypted = raw.FPDF_GetSecurityHandlerRevision(pdf.raw) != -1
		page = pdf[0]
		width, height = page.get_size()
		if not (width > 0 and height > 0):
			raise Refused(FAILED)
		scale = min(box / width, box / height, MAX_SCALE)
		bitmap = page.render(scale=scale, may_draw_forms=False)
		image = bitmap.to_pil()
	except (Refused, MemoryError):
		raise
	except Exception:
		raise Refused(FAILED) from None
	return to_webp(image, px, {"encrypted": True} if encrypted else None)
