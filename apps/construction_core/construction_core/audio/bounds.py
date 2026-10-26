"""What every audio reader shares: the refusal, the budget that bounds a walk, and byte readers that never trust a
header's claim about what follows.

The readers run in the web process on bytes a client sent (SEC-16, design §3.6), so each one walks headers and indexes
only, never decodes audio, and allocates nothing from a size a header names: every size is checked against the bytes
that are really there before it is used.
"""

import struct
import time

MAX_ITEMS = 200_000  # boxes, elements, pages and index entries walked; 300 s of Opus in 20 ms frames is 15,000 blocks
MAX_SECONDS = 2.0  # wall clock for one file; a 10 MB recording takes milliseconds
MAX_DEPTH = 8  # nesting of the containers a reader descends into


class Refused(Exception):
	"""``reason``: not_valid, unseekable, video, tracks, codec, too_long or too_complex."""

	def __init__(self, reason: str):
		super().__init__(reason)
		self.reason = reason


class Budget:
	"""A count of items and a deadline: a walk that needs more of either is refused as too complex."""

	def __init__(self, items: int = MAX_ITEMS, seconds: float = MAX_SECONDS):
		self.left = items
		self.until = time.monotonic() + seconds

	def tick(self, n: int = 1) -> None:
		self.left -= n
		if self.left < 0 or time.monotonic() > self.until:
			raise Refused("too_complex")

	@staticmethod
	def depth(depth: int) -> None:
		if depth > MAX_DEPTH:
			raise Refused("too_complex")


def agrees(stated: float, played: float) -> bool:
	"""A stated length may differ from what the packets play by a recorder's own trims (pre-skip, the last frame),
	never by more than a second or 5 %."""
	return abs(stated - played) <= max(1.0, 0.05 * played)


def need(b, at: int, n: int, end: int | None = None) -> None:
	"""``n`` bytes must exist at ``at``, inside ``end`` (the parent's end) and inside the file."""
	if at < 0 or n < 0 or at + n > (len(b) if end is None else min(end, len(b))):
		raise Refused("not_valid")


def u8(b, at: int, end: int | None = None) -> int:
	need(b, at, 1, end)
	return b[at]


def u16(b, at: int, end: int | None = None, little: bool = False) -> int:
	need(b, at, 2, end)
	return struct.unpack_from("<H" if little else ">H", b, at)[0]


def u32(b, at: int, end: int | None = None, little: bool = False) -> int:
	need(b, at, 4, end)
	return struct.unpack_from("<I" if little else ">I", b, at)[0]


def u64(b, at: int, end: int | None = None, little: bool = False) -> int:
	need(b, at, 8, end)
	return struct.unpack_from("<Q" if little else ">Q", b, at)[0]


def i16(b, at: int, end: int | None = None) -> int:
	need(b, at, 2, end)
	return struct.unpack_from(">h", b, at)[0]


def i64le(b, at: int, end: int | None = None) -> int:
	need(b, at, 8, end)
	return struct.unpack_from("<q", b, at)[0]


def raw(b, at: int, n: int, end: int | None = None) -> bytes:
	"""A short field's bytes (a type code, a magic word): ``n`` is the reader's own constant, never a header's."""
	need(b, at, n, end)
	return bytes(b[at:at + n])
