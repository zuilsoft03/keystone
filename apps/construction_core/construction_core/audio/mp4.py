"""An MP4 (ISO base media) voice note: the boxes walked to find one AAC sound track, and its length.

Two lengths are read and must agree (bounds.agrees). The stated one is the largest the file states anywhere:
``mvhd`` and ``mdhd``, the sample table's ``stts``, ``mehd``, and, for a fragmented recording whose ``mvhd`` says 0,
the end of the last fragment (``tfdt`` plus the ``trun`` sample durations, or the ``tfhd``/``trex`` defaults). The
played one is the number of AAC frames (``stsz``, and each ``trun``'s count) times 1024 samples at the mp4a entry's
own rate: no stated time can shorten it. Both count against the 300 s limit.

Only the boxes on those paths are opened; every other box is stepped over by its own size, which must fit inside its
parent. A box that states a time or a table (mvhd, mvex, tkhd, mdia, mdhd, hdlr, minf, stbl, stsd, stts, stsz, tfhd,
tfdt) may appear once in its parent. Opus in MP4 is refused: the recorder asks MP4 for AAC only (design §3.6), and
Opus there would need its packets read from the media data.
"""

from construction_core.audio.bounds import Budget, Refused, agrees, need, raw, u8, u16, u32, u64

UNKNOWN32, UNKNOWN64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF
AAC_OBJECTS = {0x40, 0x66, 0x67, 0x68}  # MPEG-4 audio, MPEG-2 AAC main, LC and SSR (ISO/IEC 14496-1 table 5)
TRUN_FIELDS = (0x100, 0x200, 0x400, 0x800)  # per-sample duration, size, flags, composition offset: 4 bytes each
AAC_FRAME = 1024  # samples an AAC-LC frame decodes to
ONCE = {b"mvhd", b"mvex", b"tkhd", b"mdia", b"mdhd", b"hdlr", b"minf", b"stbl", b"stsd", b"stts", b"stsz", b"tfhd",
	b"tfdt"}


class Mp4:
	def __init__(self, b, budget: Budget):
		self.b, self.budget = b, budget
		self.movie_scale = self.movie_length = self.fragment_length = 0
		self.tracks = []  # one dict per trak
		self.defaults = {}  # trex: track id -> default sample duration
		self.ends = {}  # track id -> the end of its last fragment, in its own time scale
		self.frames = 0  # AAC frames in the fragments
		self.moov = 0

	def read(self) -> tuple[str, float]:
		for kind, start, end in self.boxes(0, len(self.b), 0):
			if kind == b"moov":
				self.moov += 1
				self.read_moov(start, end)
			elif kind == b"moof":
				self.read_moof(start, end)
		return self.result()

	def result(self) -> tuple[str, float]:
		if self.moov != 1 or not self.tracks:
			raise Refused("not_valid")
		if any(t["handler"] == b"vide" for t in self.tracks):
			raise Refused("video")
		if len(self.tracks) != 1 or self.tracks[0]["handler"] != b"soun":
			raise Refused("tracks")
		track = self.tracks[0]
		if not track["codec"]:
			raise Refused("codec")
		if not track["scale"] or not self.movie_scale:
			raise Refused("not_valid")
		if set(self.ends) - {track["id"]}:
			raise Refused("tracks")  # fragments of a track the movie does not declare
		stated = max(self.movie_length / self.movie_scale, self.fragment_length / self.movie_scale,
			max(track["length"], track["samples"], self.ends.get(track["id"], 0)) / track["scale"])
		if not track["rate"]:
			raise Refused("not_valid")
		played = (track["frames"] + self.frames) * AAC_FRAME / track["rate"]
		if not agrees(stated, played):
			raise Refused("not_valid")
		return track["codec"], max(stated, played)

	# --- the movie ----------------------------------------------------------------------------------------------

	def read_moov(self, start: int, end: int) -> None:
		for kind, s, e in self.boxes(start, end, 1):
			if kind == b"mvhd":
				self.movie_scale, self.movie_length = self.full_times(s, e)
			elif kind == b"trak":
				self.tracks.append(self.read_trak(s, e))
			elif kind == b"mvex":
				self.read_mvex(s, e)

	def read_mvex(self, start: int, end: int) -> None:
		for kind, s, e in self.boxes(start, end, 2):
			if kind == b"mehd":
				version = u8(self.b, s, e)
				self.fragment_length = known(u64(self.b, s + 4, e) if version == 1 else u32(self.b, s + 4, e))
			elif kind == b"trex":
				self.defaults[u32(self.b, s + 4, e)] = u32(self.b, s + 12, e)

	def read_trak(self, start: int, end: int) -> dict:
		track = {"id": None, "handler": None, "codec": None, "scale": 0, "length": 0, "samples": 0, "frames": 0,
			"rate": 0}
		for kind, s, e in self.boxes(start, end, 2):
			if kind == b"tkhd":
				track["id"] = u32(self.b, s + (20 if u8(self.b, s, e) == 1 else 12), e)
			elif kind == b"mdia":
				self.read_mdia(s, e, track)
		return track

	def read_mdia(self, start: int, end: int, track: dict) -> None:
		for kind, s, e in self.boxes(start, end, 3):
			if kind == b"mdhd":
				track["scale"], track["length"] = self.full_times(s, e)
			elif kind == b"hdlr":
				track["handler"] = raw(self.b, s + 8, 4, e)
			elif kind == b"minf":
				for k2, s2, e2 in self.boxes(s, e, 4):
					if k2 == b"stbl":
						self.read_stbl(s2, e2, track)

	def read_stbl(self, start: int, end: int, track: dict) -> None:
		for kind, s, e in self.boxes(start, end, 5):
			if kind == b"stsd":
				track["codec"], track["rate"] = self.read_stsd(s, e)
			elif kind == b"stts":
				track["samples"] = self.read_stts(s, e)
			elif kind == b"stsz":
				track["frames"] = self.read_stsz(s, e)

	def read_stsd(self, start: int, end: int) -> tuple[str | None, int]:
		"""(codec, sample rate) of the one sample description; the rate is the entry's 16.16 value."""
		if u32(self.b, start + 4, end) != 1:
			raise Refused("tracks")  # one sample description: one codec
		for kind, s, e in self.boxes(start + 8, end, 6):
			if kind == b"mp4a" and self.esds_object(s, e) in AAC_OBJECTS:
				return "aac", u32(self.b, s + 24, e) >> 16
			return None, 0
		return None, 0

	def esds_object(self, start: int, end: int) -> int | None:
		"""The decoder's object type in the mp4a entry's esds box (ISO/IEC 14496-1 §7.2.6.5, 7.2.6.6)."""
		version = u16(self.b, start + 8, end)
		if version > 1:
			return None
		for kind, s, e in self.boxes(start + 28 + 16 * version, end, 7):
			if kind == b"esds":
				return esds_object(self.b, s + 4, e)
		return None

	def read_stsz(self, start: int, end: int) -> int:
		"""The sample count; its size table, when there is one, must really be there."""
		size, count = u32(self.b, start + 4, end), u32(self.b, start + 8, end)
		if not size:
			need(self.b, start + 12, 4 * count, end)
		return count

	def read_stts(self, start: int, end: int) -> int:
		count = u32(self.b, start + 4, end)
		need(self.b, start + 8, 8 * count, end)  # the entries are really there before any is read
		self.budget.tick(count)
		return sum(u32(self.b, start + 8 + 8 * i) * u32(self.b, start + 12 + 8 * i) for i in range(count))

	# --- fragments ----------------------------------------------------------------------------------------------

	def read_moof(self, start: int, end: int) -> None:
		for kind, s, e in self.boxes(start, end, 1):
			if kind == b"traf":
				self.read_traf(s, e)

	def read_traf(self, start: int, end: int) -> None:
		track, default, base, total = None, None, None, 0
		for kind, s, e in self.boxes(start, end, 2):
			if kind == b"tfhd":
				track, default = self.read_tfhd(s, e)
			elif kind == b"tfdt":
				base = u64(self.b, s + 4, e) if u8(self.b, s, e) == 1 else u32(self.b, s + 4, e)
			elif kind == b"trun":
				if track is None:
					raise Refused("not_valid")
				total += self.read_trun(s, e, default if default is not None else self.defaults.get(track, 0))
		if track is None:
			raise Refused("not_valid")
		self.ends[track] = max(self.ends.get(track, 0), (self.ends.get(track, 0) if base is None else base) + total)

	def read_tfhd(self, start: int, end: int) -> tuple[int, int | None]:
		flags = u32(self.b, start, end) & 0xFFFFFF
		at = start + 8 + (8 if flags & 0x01 else 0) + (4 if flags & 0x02 else 0)
		return u32(self.b, start + 4, end), (u32(self.b, at, end) if flags & 0x08 else None)

	def read_trun(self, start: int, end: int, default: int) -> int:
		flags = u32(self.b, start, end) & 0xFFFFFF
		count = u32(self.b, start + 4, end)
		at = start + 8 + (4 if flags & 0x01 else 0) + (4 if flags & 0x04 else 0)
		step = 4 * sum(1 for f in TRUN_FIELDS if flags & f)
		need(self.b, at, step * count, end)
		self.frames += count
		if not flags & 0x100:
			return count * default
		self.budget.tick(count)
		return sum(u32(self.b, at + step * i) for i in range(count))

	# --- boxes ------------------------------------------------------------------------------------------------

	def boxes(self, start: int, end: int, depth: int):
		"""(type, content start, end) of each box in [start, end). A size of 0 runs to the parent's end; any size
		that leaves the parent, or is smaller than its own header, is refused."""
		self.budget.depth(depth)
		at, seen = start, set()
		while at < end:
			self.budget.tick()
			kind = raw(self.b, at + 4, 4, end)
			if kind in ONCE:
				if kind in seen:
					raise Refused("not_valid")  # a second one would restate a time or a table, the last one winning
				seen.add(kind)
			size, head = u32(self.b, at, end), 8
			if size == 1:
				size, head = u64(self.b, at + 8, end), 16
			elif size == 0:
				size = end - at
			if size < head or size > end - at:
				raise Refused("not_valid")
			yield kind, at + head, at + size
			at += size

	def full_times(self, start: int, end: int) -> tuple[int, int]:
		"""(time scale, duration) of an mvhd or mdhd box, version 0 or 1; an all-ones duration means unknown."""
		if u8(self.b, start, end) == 1:
			return u32(self.b, start + 20, end), known(u64(self.b, start + 24, end))
		return u32(self.b, start + 12, end), known(u32(self.b, start + 16, end))


def known(value: int) -> int:
	return 0 if value in (UNKNOWN32, UNKNOWN64) else value


def esds_object(b, at: int, end: int) -> int | None:
	"""ES_Descriptor (tag 3) then DecoderConfigDescriptor (tag 4): its first byte is the object type."""
	if u8(b, at, end) != 0x03:
		return None
	at = descriptor_body(b, at + 1, end)
	flags = u8(b, at + 2, end)
	at += 3 + (2 if flags & 0x80 else 0)  # ES_ID and flags, then dependsOn, URL and OCR in that order
	if flags & 0x40:
		at += 1 + u8(b, at, end)
	at += 2 if flags & 0x20 else 0
	if u8(b, at, end) != 0x04:
		return None
	return u8(b, descriptor_body(b, at + 1, end), end)


def descriptor_body(b, at: int, end: int) -> int:
	"""Skip a descriptor's size field (1 to 4 bytes of 7 bits)."""
	for i in range(4):
		if not u8(b, at + i, end) & 0x80:
			return at + i + 1
	raise Refused("not_valid")


def read(b, budget: Budget) -> tuple[str, float]:
	return Mp4(b, budget).read()
