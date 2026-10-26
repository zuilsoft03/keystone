"""What every reader shares: the refusal, the result, and the one re-encode to WebP (design §15.1: at most 400 px, no
metadata). Every picture a reader finds is attacker-chosen bytes, so it is decoded under a pixel cap and drawn again."""

import struct
import warnings
from dataclasses import dataclass, field
from io import BytesIO

# Fixed reasons: stored for the hash and renderer version, never retried (§15.3). The card's words are the screen's.
LOCKED, TOO_LARGE, BLANK, FAILED, NOT_SUPPORTED = "locked", "too_large", "blank", "failed", "not_supported"
REASONS = (LOCKED, TOO_LARGE, BLANK, FAILED, NOT_SUPPORTED)
MAX_SOURCE_PIXELS = 50_000_000  # an image file: the client limit (client_files.MAX_PIXELS)
MAX_EMBEDDED_PIXELS = 4_000_000  # a picture inside a file (DWG, RVT): real ones are at most a few hundred pixels
MAX_EMBEDDED_SIDE = 4096
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PLUGINS = {"JPEG": "JpegImagePlugin", "PNG": "PngImagePlugin", "WEBP": "WebPImagePlugin",
	"BMP": "BmpImagePlugin"}


class Refused(Exception):
	"""No preview, for a fixed reason. ``meta``: what the card may still show (IFC: schema and app)."""

	def __init__(self, reason: str, meta: dict | None = None):
		super().__init__(reason)
		self.reason = reason if reason in REASONS else FAILED
		self.meta = meta or {}


@dataclass
class Result:
	webp: bytes
	width: int
	height: int
	meta: dict = field(default_factory=dict)


def to_webp(image, px: int, meta: dict | None = None) -> Result:
	"""The preview: RGB or RGBA, at most ``px`` on its long edge, WebP with no metadata at all."""
	from PIL import Image

	if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
		image = image.convert("RGBA")
	elif image.mode != "RGB":
		image = image.convert("RGB")
	image.thumbnail((px, px), Image.Resampling.LANCZOS)
	image.info = {}
	out = BytesIO()
	image.save(out, "WEBP", quality=80, method=4)
	return Result(out.getvalue(), image.width, image.height, meta or {})


def open_embedded(data: bytes, formats: tuple[str, ...]):
	"""A picture found inside a file, decoded under a small pixel cap. Refused when it is not one of ``formats``."""
	from PIL import Image

	image = open_capped(BytesIO(data), MAX_EMBEDDED_PIXELS, formats)
	if image.width > MAX_EMBEDDED_SIDE or image.height > MAX_EMBEDDED_SIDE:
		raise Refused(TOO_LARGE)
	image.load()
	if isinstance(image, Image.Image) and is_blank(image):
		raise Refused(BLANK)
	return image


def open_capped(fh, max_pixels: int, formats: tuple[str, ...]):
	"""Image.open with the header checked before any pixel is decoded: format and pixel count. Only the plugins of
	``formats`` are loaded, so no other decoder can claim the bytes."""
	import importlib

	from PIL import Image

	for name in formats:
		importlib.import_module(f"PIL.{PLUGINS[name]}")
	# Pillow's own bomb limit stays as it is (a process-wide setting the backend's other code relies on); the cap here is
	# checked on the header, before any pixel is decoded
	with warnings.catch_warnings():
		warnings.simplefilter("error", Image.DecompressionBombWarning)
		try:
			image = Image.open(fh, formats=list(formats))
		except (Image.DecompressionBombError, Image.DecompressionBombWarning):
			raise Refused(TOO_LARGE) from None
		except Exception:
			raise Refused(FAILED) from None
	if image.width * image.height > max_pixels or image.width < 1 or image.height < 1:
		raise Refused(TOO_LARGE)
	return image


def is_blank(image) -> bool:
	"""One colour everywhere: a preview a tool wrote without drawing (measured: all black in tool-written DWGs)."""
	return image.convert("RGB").getcolors(1) is not None


def png_slice(data: bytes) -> bytes:
	"""The PNG inside ``data``, from its signature to the end of its IEND chunk, walked chunk by chunk (the bytes
	"IEND" can also appear inside image data, so a search for them is not enough)."""
	start = data.find(PNG_SIGNATURE)
	if start < 0:
		raise Refused(BLANK)
	at = start + len(PNG_SIGNATURE)
	while at + 12 <= len(data):
		length, kind = struct.unpack_from(">I4s", data, at)
		at += 12 + length
		if at > len(data):
			break
		if kind == b"IEND":
			return data[start:at]
	raise Refused(FAILED)
