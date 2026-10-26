"""A WebM voice note: the EBML elements walked to find one Opus track and the time of the last block.

Two lengths are read and must agree (bounds.agrees). The stated one is the larger of the Info ``Duration`` and the
end of the last block (its cluster's ``Timecode`` plus its own relative time and any ``BlockDuration``), in
``TimecodeScale`` units. The played one is every Opus packet's own duration from its TOC byte, each frame of a laced
block counted. Both count against the 300 s limit, so a rewritten scale or timecode cannot shorten a long note.

Only the Segment and a Cluster may have an unknown size (a recorder writes them before it knows how long it ran); an
unknown-size Cluster ends where the next Segment-level element starts. A Segment of unknown size with no ``Cues``
cannot be seeked by Chromium or Firefox (P3-67's playback matrix), so it is refused: the recorder records it again.
One Info and one Tracks only, the track's CodecPrivate an OpusHead of one or two channels, and no bytes after a
Segment of known size.
"""

import struct

from construction_core.audio import opus
from construction_core.audio.bounds import Budget, Refused, agrees, i16, need, raw, u8

EBML, SEGMENT = 0x1A45DFA3, 0x18538067
INFO, TRACKS, CUES, CLUSTER = 0x1549A966, 0x1654AE6B, 0x1C53BB6B, 0x1F43B675
SEEKHEAD, TAGS, CHAPTERS, ATTACHMENTS, VOID, CRC = 0x114D9B74, 0x1254C367, 0x1043A770, 0x1941A469, 0xEC, 0xBF
SEGMENT_CHILDREN = {SEEKHEAD, INFO, TRACKS, CUES, CLUSTER, TAGS, CHAPTERS, ATTACHMENTS}  # end an unknown Cluster
DOCTYPE, SCALE, DURATION = 0x4282, 0x2AD7B1, 0x4489
TRACK_ENTRY, TRACK_NUMBER, TRACK_TYPE, CODEC, CODEC_PRIVATE = 0xAE, 0xD7, 0x83, 0x86, 0x63A2
TIMECODE, SIMPLE_BLOCK, BLOCK_GROUP, BLOCK, BLOCK_DURATION = 0xE7, 0xA3, 0xA0, 0xA1, 0x9B
AUDIO, VIDEO = 2, 1
NO_LACING, XIPH, FIXED, EBML_LACING = 0, 1, 2, 3
NUMBER_MAX = 8  # an unsigned integer element of more bytes is not one a recorder writes


class WebM:
	def __init__(self, b, budget: Budget):
		self.b, self.budget = b, budget
		self.scale, self.duration = 1_000_000, 0.0
		self.tracks = []
		self.cues = False
		self.last = 0  # the end of the latest block, in TimecodeScale units
		self.played = 0  # samples at 48 kHz, from the packets' TOC bytes
		self.seen = set()  # Info and Tracks: one each

	def read(self) -> tuple[str, float]:
		at = self.read_header()
		element, start, end, unknown = self.element(at, len(self.b), allow_unknown=True)
		if element != SEGMENT:
			raise Refused("not_valid")
		self.read_segment(start, end)
		if unknown and not self.cues:
			raise Refused("unseekable")
		if not unknown and end != len(self.b):
			raise Refused("not_valid")  # bytes after the Segment
		return self.result()

	def result(self) -> tuple[str, float]:
		self.check_tracks()
		stated = max(self.duration, self.last) * self.scale / 1e9
		played = self.played / opus.RATE
		if not agrees(stated, played):
			raise Refused("not_valid")
		return "opus", max(stated, played)

	def check_tracks(self) -> None:
		if any(t["type"] == VIDEO for t in self.tracks):
			raise Refused("video")
		if len(self.tracks) != 1 or self.tracks[0]["type"] != AUDIO:
			raise Refused("tracks")
		if self.tracks[0]["codec"] != b"A_OPUS" or not opus.channels_ok(self.tracks[0]["private"] or b""):
			raise Refused("codec")

	def read_header(self) -> int:
		element, start, end, _unknown = self.element(0, len(self.b))
		if element != EBML:
			raise Refused("not_valid")
		doctype = None
		for e, s, t in self.children(start, end, 1):
			if e == DOCTYPE:
				doctype = raw(self.b, s, min(t - s, 16), t)
		if doctype != b"webm":
			raise Refused("not_valid")
		return end

	def read_segment(self, start: int, end: int) -> None:
		at = start
		while at < end:
			self.budget.tick()
			element, s, e, unknown = self.element(at, end, allow_unknown=True)
			if unknown and element != CLUSTER:
				raise Refused("not_valid")
			if element in (INFO, TRACKS):
				if element in self.seen:
					raise Refused("not_valid")  # a second Info or Tracks would restate the scale or the track
				self.seen.add(element)
			if element == CLUSTER:
				at = self.read_cluster(s, e, unknown)
				continue
			if element == INFO:
				self.read_info(s, e)
			elif element == TRACKS:
				self.read_tracks(s, e)
			elif element == CUES:
				self.cues = True
			elif element == ATTACHMENTS:
				raise Refused("not_valid")  # a voice note carries no files
			at = e

	def read_info(self, start: int, end: int) -> None:
		for e, s, t in self.children(start, end, 2):
			if e == SCALE:
				self.scale = self.number(s, t)
				if not 1 <= self.scale <= 1_000_000_000:
					raise Refused("not_valid")
			elif e == DURATION:
				self.duration = self.float(s, t)

	def read_tracks(self, start: int, end: int) -> None:
		for e, s, t in self.children(start, end, 2):
			if e == TRACK_ENTRY:
				track = {"number": None, "type": None, "codec": None, "private": None}
				for e2, s2, t2 in self.children(s, t, 3):
					if e2 == TRACK_NUMBER:
						track["number"] = self.number(s2, t2)
					elif e2 == TRACK_TYPE:
						track["type"] = self.number(s2, t2)
					elif e2 == CODEC:
						track["codec"] = raw(self.b, s2, min(t2 - s2, 16), t2)
					elif e2 == CODEC_PRIVATE:
						track["private"] = raw(self.b, s2, min(t2 - s2, 19), t2)
				self.tracks.append(track)
		self.check_tracks()  # before any block is read: one Opus track, no video

	def read_cluster(self, start: int, end: int, unknown: bool) -> int:
		"""Walks the cluster's blocks; returns where the cluster ends."""
		base, at = None, start
		while at < end:
			self.budget.tick()
			if unknown and self.id_at(at, end) in SEGMENT_CHILDREN:
				return at
			element, s, e, _unknown = self.element(at, end)
			if element == TIMECODE:
				base = self.number(s, e)
			elif element == SIMPLE_BLOCK:
				self.block(base, s, e, 0)
			elif element == BLOCK_GROUP:
				self.read_group(base, s, e)
			at = e
		return end

	def read_group(self, base, start: int, end: int) -> None:
		block, length = None, 0
		for e, s, t in self.children(start, end, 3):
			if e == BLOCK:
				block = (s, t)
			elif e == BLOCK_DURATION:
				length = self.number(s, t)
		if block:
			self.block(base, *block, length)

	def block(self, base, start: int, end: int, length: int) -> None:
		"""A block names its track and its time relative to the cluster's Timecode."""
		if base is None or len(self.tracks) != 1:
			raise Refused("not_valid")  # a block before its cluster's time, or before the one track is declared
		track, size = self.vint(start, end, mask=True)
		if track != self.tracks[0]["number"]:
			raise Refused("tracks")
		self.last = max(self.last, base + i16(self.b, start + size, end) + length)
		at = start + size + 2
		lacing = (u8(self.b, at, end) >> 1) & 3
		for frame, frame_end in self.frames(at + 1, end, lacing):
			self.packet(frame, frame_end)

	def frames(self, at: int, end: int, lacing: int) -> list[tuple[int, int]]:
		"""(start, end) of each frame of a block: one, or a lace of up to 256 (Matroska's Xiph, fixed-size and EBML
		lacing). Every size must be at least one byte and the sizes must fill the block exactly."""
		if lacing == NO_LACING:
			sizes = [end - at]
		else:
			count = u8(self.b, at, end) + 1
			at += 1
			if lacing == FIXED:
				if (end - at) % count:
					raise Refused("not_valid")
				sizes = [(end - at) // count] * count
			else:
				sizes, at = self.lace(at, end, lacing, count)
				sizes.append(end - at - sum(sizes))
		if min(sizes) < 1 or sum(sizes) != end - at:
			raise Refused("not_valid")
		out = []
		for n in sizes:
			out.append((at, at + n))
			at += n
		return out

	def lace(self, at: int, end: int, lacing: int, count: int) -> tuple[list[int], int]:
		"""The first count - 1 sizes of a Xiph or EBML lace, and where the frames start."""
		sizes = []
		if lacing == XIPH:
			for _i in range(count - 1):
				size = 0
				while True:
					self.budget.tick()
					value = u8(self.b, at, end)
					at, size = at + 1, size + value
					if value < 255:
						break
				sizes.append(size)
		elif lacing == EBML_LACING and count > 1:
			first, n = self.vint(at, end, mask=True)
			at, sizes = at + n, [first]
			for _i in range(count - 2):
				value, n = self.vint(at, end, mask=True)
				at += n
				sizes.append(sizes[-1] + value - ((1 << (7 * n - 1)) - 1))  # a signed difference from the last
		return sizes, at

	def packet(self, start: int, end: int) -> None:
		self.budget.tick()
		toc = u8(self.b, start, end)
		self.played += opus.samples(toc, u8(self.b, start + 1, end) if opus.needs_count(toc) else None)

	# --- elements ---------------------------------------------------------------------------------------------

	def children(self, start: int, end: int, depth: int):
		"""(id, data start, data end) of each child of a known-size element; a child of unknown size is refused."""
		self.budget.depth(depth)
		at = start
		while at < end:
			self.budget.tick()
			element, s, e, _unknown = self.element(at, end)
			yield element, s, e
			at = e

	def element(self, at: int, end: int, allow_unknown: bool = False) -> tuple[int, int, int, bool]:
		"""(id, data start, data end, unknown size). A size that leaves the parent is refused; an unknown size runs to
		the parent's end, and only where the caller allows one."""
		element, n = self.vint(at, end, mask=False)
		if n > 4:
			raise Refused("not_valid")
		size, m = self.vint(at + n, end, mask=True)
		start = at + n + m
		unknown = size == (1 << (7 * m)) - 1
		if unknown:
			if not allow_unknown:
				raise Refused("not_valid")
			return element, start, end, True
		if size > end - start:
			raise Refused("not_valid")
		return element, start, start + size, False

	def id_at(self, at: int, end: int) -> int:
		return self.vint(at, end, mask=False)[0]

	def vint(self, at: int, end: int, mask: bool) -> tuple[int, int]:
		first = u8(self.b, at, end)
		if not first:
			raise Refused("not_valid")  # a length of more than 8 bytes
		n = 9 - first.bit_length()
		need(self.b, at, n, end)
		value = first & ((1 << (8 - n)) - 1) if mask else first
		for i in range(1, n):
			value = (value << 8) | self.b[at + i]
		return value, n

	def number(self, start: int, end: int) -> int:
		if end - start > NUMBER_MAX:
			raise Refused("not_valid")
		return int.from_bytes(raw(self.b, start, end - start, end), "big")

	def float(self, start: int, end: int) -> float:
		if end - start not in (0, 4, 8):
			raise Refused("not_valid")
		if end == start:
			return 0.0
		value = struct.unpack(">f" if end - start == 4 else ">d", raw(self.b, start, end - start, end))[0]
		if value != value or value < 0 or value == float("inf"):
			raise Refused("not_valid")
		return value


def read(b, budget: Budget) -> tuple[str, float]:
	return WebM(b, budget).read()
