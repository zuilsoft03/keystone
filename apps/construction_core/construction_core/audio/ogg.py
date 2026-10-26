"""An Ogg Opus voice note: its pages walked end to end, one logical stream, OpusHead first.

Each page's size comes from its own segment table, and the page must fit in the bytes left; the walk does not
resynchronise, so any byte that is not a page is refused. Two lengths are read and must agree (bounds.agrees): the
stated one, the largest granule position less OpusHead's pre-skip at Opus's fixed 48 kHz (RFC 7845 §4), and the
played one, every audio packet's own duration from its TOC byte (the lacing values give the packet boundaries). Both
count against the 300 s limit, so a rewritten granule cannot shorten a long note. CRCs are not checked: the player
does that, and a bad one changes nothing here.
"""

from construction_core.audio import opus
from construction_core.audio.bounds import Budget, Refused, agrees, i64le, need, raw, u8, u16, u32

HEADER = 27
CONTINUED, BOS = 0x01, 0x02
NO_GRANULE = -1  # a page on which no packet ends
HEADERS = 2  # OpusHead and OpusTags come before the audio packets


class Ogg:
	def __init__(self, b, budget: Budget):
		self.b, self.budget = b, budget
		self.serial, self.skip, self.granule = None, 0, 0
		self.packets, self.played = 0, 0  # audio packets seen, and their samples
		self.head, self.open = b"", False  # the current packet's first two bytes, and whether it runs on

	def read(self) -> tuple[str, float]:
		at = 0
		while at < len(self.b):
			self.budget.tick()
			at = self.page(at)
		if self.serial is None:
			raise Refused("not_valid")
		stated = max(0, self.granule - self.skip) / opus.RATE
		played = max(0, self.played - self.skip) / opus.RATE
		if not agrees(stated, played):
			raise Refused("not_valid")
		return "opus", max(stated, played)

	def page(self, at: int) -> int:
		b = self.b
		if raw(b, at, 4) != b"OggS" or u8(b, at + 4) != 0:
			raise Refused("not_valid")
		flags, position, stream = u8(b, at + 5), i64le(b, at + 6), u32(b, at + 14, little=True)
		segments = u8(b, at + 26)
		need(b, at + HEADER, segments)
		body = at + HEADER + segments
		end = body + sum(b[at + HEADER:body])
		need(b, body, end - body)
		if self.serial is None:
			if not flags & BOS:
				raise Refused("not_valid")
			self.serial, self.skip = stream, opus_head(b, body, end)
		elif stream != self.serial or flags & BOS:
			raise Refused("tracks")  # a second logical stream: another track, perhaps video
		if bool(flags & CONTINUED) != self.open:
			raise Refused("not_valid")  # a packet cut off, or a continuation of nothing
		if position != NO_GRANULE:
			if position < 0:
				raise Refused("not_valid")
			self.granule = max(self.granule, position)
		self.read_packets(at + HEADER, body)
		return end

	def read_packets(self, lacing: int, body: int) -> None:
		"""Each lacing value is a segment; one under 255 ends its packet (RFC 3533 §5)."""
		at = body
		for i in range(lacing, body):
			size = self.b[i]
			if not self.open:
				self.head, self.open = b"", True
			if len(self.head) < 2:
				self.head += raw(self.b, at, min(size, 2 - len(self.head)))
			at += size
			if size < 255:
				self.end_packet()

	def end_packet(self) -> None:
		self.open = False
		self.packets += 1
		if self.packets <= HEADERS:
			return
		self.budget.tick()
		if not self.head:
			raise Refused("not_valid")  # an Opus packet has at least its TOC byte
		toc = self.head[0]
		if opus.needs_count(toc) and len(self.head) < 2:
			raise Refused("not_valid")
		self.played += opus.samples(toc, self.head[1] if len(self.head) > 1 else None)


def opus_head(b, start: int, end: int) -> int:
	"""The first packet is OpusHead, mono or stereo; returns the pre-skip. A Vorbis, Theora or any other first packet
	is not a voice note's codec."""
	if not opus.channels_ok(raw(b, start, min(19, end - start), end)):
		raise Refused("codec")
	return u16(b, start + 10, end, little=True)


def read(b, budget: Budget) -> tuple[str, float]:
	return Ogg(b, budget).read()
