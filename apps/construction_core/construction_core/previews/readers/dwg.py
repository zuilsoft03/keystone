"""The picture a DWG keeps of itself (design §15.2): a DIB up to R2010, a PNG from R2013. Found through the image
seeker at 0x0D, checked against its sentinel, every address and size bounds-checked against the file. A drawing with
no picture, or one of a single colour (tool-written files carry an all-black one, measured), gets the placeholder."""

import re
import struct

from construction_core.previews.readers.common import BLANK, FAILED, Refused, open_embedded, to_webp

SENTINEL = bytes.fromhex("1F256D07D43628289D57CA3F9D44102B")
SEEKER = 0x0D
CODE_DIB, CODE_PNG = 2, 6
MAX_ENTRIES = 8
MAX_PICTURE = 2 * 1024 * 1024


def render(fh, px: int):
	size = _size(fh)
	head = _read(fh, 0, 0x20, size)
	if re.match(rb"AC10\d\d", head[:6]) is None:
		raise Refused(FAILED)
	seeker = struct.unpack_from("<I", head, SEEKER)[0]
	if seeker < 0x19 or seeker + len(SENTINEL) + 5 > size:
		raise Refused(BLANK)
	if _read(fh, seeker, len(SENTINEL), size) != SENTINEL:
		raise Refused(BLANK)
	pictures = _entries(fh, seeker + len(SENTINEL), size)
	code, start, length = pictures.get(CODE_PNG) or pictures.get(CODE_DIB) or (None, 0, 0)
	if code is None:
		raise Refused(BLANK)  # no picture, or a WMF only
	data = _read(fh, start, length, size)
	if code == CODE_DIB:
		return to_webp(open_embedded(_bmp(data), ("BMP",)), px)
	return to_webp(open_embedded(data, ("PNG",)), px)


def _entries(fh, at: int, size: int) -> dict:
	"""{code: (code, start, size)} of the pictures the table lists, each inside the file and under MAX_PICTURE."""
	_overall, count = struct.unpack("<IB", _read(fh, at, 5, size))
	if count > MAX_ENTRIES:
		raise Refused(FAILED)
	table = _read(fh, at + 5, count * 9, size)
	found = {}
	for i in range(count):
		code, start, length = struct.unpack_from("<BII", table, i * 9)
		if code in (CODE_DIB, CODE_PNG) and 0 < length <= MAX_PICTURE and start + length <= size and start > 0:
			found.setdefault(code, (code, start, length))
	return found


def _bmp(dib: bytes) -> bytes:
	"""A DIB with the 14-byte file header Pillow needs: where the pixels start is the header plus the palette."""
	if len(dib) < 16:
		raise Refused(FAILED)
	header = struct.unpack_from("<I", dib, 0)[0]
	if header not in (12, 40, 52, 56, 108, 124) or header > len(dib):
		raise Refused(FAILED)
	if header == 12:
		bits, colours, entry = struct.unpack_from("<H", dib, 10)[0], 0, 3
	else:
		bits, colours, entry = struct.unpack_from("<H", dib, 14)[0], struct.unpack_from("<I", dib, 32)[0], 4
	if bits not in (1, 4, 8, 16, 24, 32):
		raise Refused(FAILED)
	if bits <= 8:
		colours = colours or (1 << bits)
	if colours > 256:
		raise Refused(FAILED)
	offset = 14 + header + colours * entry
	if header == 40 and struct.unpack_from("<I", dib, 16)[0] in (3, 6):
		offset += 12  # the colour masks follow a plain header (BI_BITFIELDS)
	if offset > 14 + len(dib):
		raise Refused(FAILED)
	return b"BM" + struct.pack("<IHHI", 14 + len(dib), 0, 0, offset) + dib


def _size(fh) -> int:
	fh.seek(0, 2)
	return fh.tell()


def _read(fh, at: int, length: int, size: int) -> bytes:
	if at < 0 or length < 0 or at + length > size:
		raise Refused(FAILED)
	fh.seek(at)
	data = fh.read(length)
	if len(data) != length:
		raise Refused(FAILED)
	return data
