"""JPEG, PNG and WebP from Files (design §15.2): the header first (format, at most 50 megapixels), then one decode. A
JPEG is decoded at a reduced size (libjpeg's DCT scaling), so a 50 MP photo never needs its full bitmap. A converter's
page (the Document Server's PNG of an Office file) is drawn the same way, and a page of one colour is the placeholder."""

from PIL import ImageOps

from construction_core.previews.readers.common import (BLANK, FAILED, MAX_SOURCE_PIXELS, Refused, is_blank,
	open_capped, to_webp)

FORMATS = ("JPEG", "PNG", "WEBP")  # a phone's MPO opens through the JPEG plugin


def render(fh, px: int):
	image = _decoded(fh, px, FORMATS)
	return to_webp(image, px)


def render_page(fh, px: int):
	image = _decoded(fh, px, ("PNG",))
	result = to_webp(image.copy(), px)
	image.thumbnail((px, px))
	if is_blank(image):
		raise Refused(BLANK)
	return result


def _decoded(fh, px: int, formats):
	image = open_capped(fh, MAX_SOURCE_PIXELS, formats)
	try:
		if image.format in ("JPEG", "MPO"):
			image.draft("RGB", (px * 2, px * 2))
		image.load()
		return ImageOps.exif_transpose(image)
	except (Refused, MemoryError):
		raise
	except Exception:
		raise Refused(FAILED) from None
