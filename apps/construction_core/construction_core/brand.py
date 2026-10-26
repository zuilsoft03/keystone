"""P3-45 (D-300, D-344, D-401…D-404, D-445): the firm's brand from the owner's Brand page.

Brand Settings (a Single, System Managers only) holds the firm's name, logo, main colour, brand panel colour, heading
font and the default sign-in picture. Every page and mail reads it through ``public()``; with nothing set every value is
"" and Keystone leads, as before (D-403). The product's name is never set here (D-445), and nothing here hides the
"Powered by Keystone" credit (D-404). A colour reaches CSS only as a checked #RRGGBB, a font only as a key of FONTS.
"""

import hashlib
import os
import re

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import get_files_path

DOCTYPE = "Brand Settings"
CACHE_KEY = "cc_brand_settings"  # one shared Redis key (the stored row only; the config fallback is read live)
FIELDS = ("company_name", "logo", "main_colour", "panel_colour", "heading_font", "signin_picture")
IMAGES = {"logo": "logo", "signin": "signin_picture"}  # set_image's kind -> its field
FONTS = ("archivo", "barlow-semi-condensed", "manrope", "ibm-plex-sans")  # self-hosted in the shell (D-467)
INK_GRAY_8 = "#171717"  # frappe-ui ink-gray-8, oklch(0.205 0 0): the darkest a button may be (no black buttons)
HOVER, PRESS = 0.06, 0.12  # how far towards white the hover and press shades go: lighter, never darker
MIN_CONTRAST = 4.5  # WCAG 2.x AA for white button text
HEX = re.compile(r"^#[0-9A-F]{6}$")
IMAGE_URL = re.compile(r"^/files/brand-[0-9a-f]{16}\.(png|jpg|webp)$")


def stored() -> dict:
	"""The saved row, every field a string ("" when unset), from the one shared cache key."""
	def load():
		row = frappe.db.get_singles_dict(DOCTYPE) if frappe.db.exists("DocType", DOCTYPE) else {}
		return {f: str(row.get(f) or "") for f in FIELDS}

	return frappe.cache.get_value(CACHE_KEY, generator=load)


def clear_cache() -> None:
	frappe.cache.delete_value(CACHE_KEY)


def public() -> dict:
	"""What every boot and mail may show; "" for each value not set (heading_font: Keystone's Archivo)."""
	from construction_core.onboarding.mail import brand as company

	row = stored()
	hover, press = shades(row["main_colour"]) if row["main_colour"] else ("", "")
	return {"company": company(), "logo_url": row["logo"], "main": row["main_colour"], "main_hover": hover,
		"main_press": press, "panel": row["panel_colour"], "heading_font": row["heading_font"] or FONTS[0],
		"signin_picture": row["signin_picture"]}


def _rgb(hex_colour: str) -> tuple[int, int, int]:
	return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def luminance(hex_colour: str) -> float:
	"""WCAG 2.x relative luminance."""
	def linear(c):
		c /= 255
		return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

	r, g, b = (linear(c) for c in _rgb(hex_colour))
	return 0.2126 * r + 0.7152 * g + 0.0722 * b


def white_contrast(hex_colour: str) -> float:
	return 1.05 / (luminance(hex_colour) + 0.05)


def shades(main: str) -> tuple[str, str]:
	"""The hover and press shades of a main colour: mixed towards white, so both are lighter (no black buttons)."""
	def mix(amount):
		return "#" + "".join(f"{round(c + (255 - c) * amount):02X}" for c in _rgb(main))

	return mix(HOVER), mix(PRESS)


def check_colour(value: str, label: str, button: bool) -> str:
	"""A colour as #RRGGBB (upper case), or "" for Keystone's; refused when white text on it (and, for the main colour,
	on its hover and press shades) is under 4.5:1, or when a button colour is darker than ink-gray-8."""
	value = (value or "").strip().upper()
	if not value:
		return ""
	if not HEX.match(value):
		frappe.throw(_("{0}: enter a colour as # and six hex digits, like #1F5FD6.").format(label))
	for colour in (value, *shades(value)) if button else (value,):
		if white_contrast(colour) < MIN_CONTRAST:
			frappe.throw(_("{0}: white text on {1} is too faint (under 4.5:1). Choose a darker colour.").format(label, colour))
		if button and luminance(colour) < luminance(INK_GRAY_8):
			frappe.throw(_("{0}: {1} is darker than the darkest button allowed. Choose a lighter colour.").format(label, colour))
	return value


def check_image(url: str, field: str) -> None:
	"""A logo or sign-in picture is only an address set_image wrote: its name pattern and its public File here."""
	if url and not (IMAGE_URL.match(url) and frappe.db.exists("File", {"file_url": url, "is_private": 0,
			"attached_to_doctype": DOCTYPE, "attached_to_field": field})):
		frappe.throw(_("Upload the image on the Brand page."))


@frappe.whitelist(methods=["POST"])
def update(company_name: str | None = None, main_colour: str | None = None, panel_colour: str | None = None,
		heading_font: str | None = None, reset: int | str = 0) -> dict:
	"""The Brand page's one call (D-344): it changes only the fields it is given ("" clears one); ``reset`` returns every
	field, the images too, to Keystone's."""
	frappe.only_for("System Manager")
	doc = frappe.get_single(DOCTYPE)
	if frappe.utils.cint(reset):
		doc.update({f: "" for f in FIELDS})
	given = {"company_name": company_name, "main_colour": main_colour, "panel_colour": panel_colour,
		"heading_font": heading_font}
	doc.update({k: v for k, v in given.items() if v is not None})
	doc.save(ignore_permissions=True)  # the role was checked above; validate() checks every value
	return public()


@frappe.whitelist(methods=["POST"])
def set_image(kind: str) -> dict:
	"""Upload the logo or the default sign-in picture (multipart field ``file``): PNG, JPEG or WebP by its bytes (never
	SVG), rebuilt from its pixels by the sign-in pictures' own public_copy (size checked before decoding, no metadata).
	Only the rebuilt bytes are stored, as a public File named by their hash; the upload itself is never kept."""
	from construction_core.signin_pictures import MAX_SOURCE, public_copy

	frappe.only_for("System Manager")
	field = _field(kind)
	sent = frappe.request.files.get("file") if getattr(frappe, "request", None) else None
	original = sent.stream.read(MAX_SOURCE + 1) if sent else b""
	if len(original) > MAX_SOURCE:
		frappe.throw(_("The image is larger than 15 MB. Use a smaller copy."))
	ext = _sniff(original)
	if not ext:
		frappe.throw(_("Choose a PNG, JPEG or WebP image."))
	try:
		content = public_copy(original, ext)
	except frappe.ValidationError:
		raise
	except Exception:  # Pillow's own decompression-bomb refusal lands here too
		frappe.throw(_("This image could not be read."))
	doc = frappe.get_single(DOCTYPE)
	url = f"/files/brand-{hashlib.sha256(content).hexdigest()[:16]}.{ext}"
	if not frappe.db.exists("File", {"file_url": url, "attached_to_doctype": DOCTYPE, "attached_to_field": field}):
		_write_public(url.rpartition("/")[2], content)
		# public, outside the storage provider (which stores private files only): every visitor's sign-in page shows
		# it. Our own address and bytes: Frappe must neither rename it nor point it at another File with the same bytes.
		f = frappe.get_doc({"doctype": "File", "file_name": url.rpartition("/")[2], "file_url": url, "is_private": 0,
			"content_hash": get_content_hash(content), "file_size": len(content),
			"attached_to_doctype": DOCTYPE, "attached_to_name": DOCTYPE, "attached_to_field": field})
		f.flags.copy_from_existing_file = True
		f.insert(ignore_permissions=True)
	doc.set(field, url)
	doc.save(ignore_permissions=True)
	return public()


@frappe.whitelist(methods=["POST"])
def clear_image(kind: str) -> dict:
	frappe.only_for("System Manager")
	doc = frappe.get_single(DOCTYPE)
	doc.set(_field(kind), "")
	doc.save(ignore_permissions=True)
	return public()


def _field(kind: str) -> str:
	if kind not in IMAGES:
		frappe.throw(_("Choose the logo or the sign-in picture."))
	return IMAGES[kind]


def _write_public(name: str, content: bytes) -> None:
	"""The rebuilt bytes at public/files/<name>. The name is their hash, so a file already there holds the same bytes
	(the logo and the sign-in picture may share one); a new one is removed again if the request rolls back."""
	path = get_files_path(name)
	try:
		fh = open(path, "xb")
	except FileExistsError:
		return
	frappe.db.after_rollback.add(lambda: os.path.exists(path) and os.remove(path))
	with fh:
		fh.write(content)


def _sniff(content: bytes) -> str:
	"""The image type from its first bytes, never from a name; "" for anything else (an SVG included)."""
	if content.startswith(b"\x89PNG\r\n\x1a\n"):
		return "png"
	if content.startswith(b"\xff\xd8\xff"):
		return "jpg"
	if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
		return "webp"
	return ""


def drop_images(before: dict, doc) -> None:
	"""The image Files a save no longer points at (replaced, cleared or reset)."""
	keep = {doc.get(f) for f in IMAGES.values()} - {""}
	for field in IMAGES.values():
		old = before.get(field)
		if old and old not in keep:
			for name in frappe.get_all("File", filters={"file_url": old, "attached_to_doctype": DOCTYPE}, pluck="name"):
				frappe.delete_doc("File", name, ignore_permissions=True, force=True)
