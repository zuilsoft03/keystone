"""A reader of OLE2 compound files (MS-CFB), standard library only (design §15.4, §15.7: no olefile). Revit files are
compound files; the preview reads one stream of them and the client check walks their directory.

Every walk is bounded: a sector chain never takes more steps than the FAT has entries (a chain that loops is
refused, the bug class of CVE-2026-59933 and CVE-2007-2650), every sector lies inside the file, the directory and
any stream read have caps, and nothing is read that the caller did not ask for. The tables are sized from the file,
never from its header: no more FAT, DIFAT or mini FAT sectors than the file could need, and the FAT kept as a compact
array of at most one entry per sector (P3-75 audit: a header that names every sector as a FAT sector would otherwise
make one request build millions of numbers). The client check runs this in the upload request, so it must stay small:
for a 250 MB file at most about 2 MB of tables."""

import struct
from array import array
from dataclasses import dataclass

from construction_core.previews.readers.common import FAILED, TOO_LARGE, Refused

MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
END, FREE = 0xFFFFFFFE, 0xFFFFFFFF
MAX_REGULAR = 0xFFFFFFFA
MAX_DIR_ENTRIES = 16384  # measured: Revit files have 32
STORAGE, STREAM, ROOT = 1, 2, 5


@dataclass
class Entry:
	name: str
	kind: int
	start: int
	size: int


class Compound:
	"""The directory of a compound file, and its streams read on demand."""

	def __init__(self, fh, size: int):
		self.fh, self.size = fh, size
		h = self._at(0, 512)
		if h[:8] != MAGIC or h[28:30] != b"\xfe\xff":
			raise Refused(FAILED)
		major = struct.unpack_from("<H", h, 26)[0]
		shift, mini_shift = struct.unpack_from("<HH", h, 30)
		if (major, shift) not in ((3, 9), (4, 12)) or mini_shift != 6:
			raise Refused(FAILED)
		self.major, self.ss, self.mss = major, 1 << shift, 64
		self.sectors = max(0, -(-(size - self.ss) // self.ss))  # a writer may leave the last sector short
		n_fat, first_dir, _sig, self.cutoff, first_mini, n_mini, first_difat, n_difat = struct.unpack_from("<IIIIIIII", h, 44)
		per = self.ss // 4  # entries in one table sector
		most_fat = -(-self.sectors // per) + 1  # one FAT entry per sector of the file, no more
		most_difat = -(-max(0, n_fat - 109) // (per - 1)) + 1
		most_mini = -(-(self.sectors * self.ss // self.mss) // per) + 1  # one mini FAT entry per 64 bytes of the file
		if (self.cutoff != 4096 or not 1 <= n_fat <= most_fat or n_difat > most_difat or n_mini > most_mini
				or self.sectors < 1):
			raise Refused(FAILED)
		self.fat = self._fat(h, n_fat, first_difat, n_difat)
		self.entries = self._directory(first_dir)
		self.minifat = self._ints(self._chain_bytes(first_mini, n_mini)) if n_mini else array("I")
		self._mini_sectors = None

	def find(self, name: str, kind: int = STREAM) -> Entry | None:
		return next((e for e in self.entries if e.kind == kind and e.name == name), None)

	def names(self, kind: int | None = None) -> set[str]:
		return {e.name for e in self.entries if kind is None or e.kind == kind}

	def read(self, entry: Entry, cap: int) -> bytes:
		"""A stream's bytes, refused as too large above ``cap``."""
		if entry.size > cap:
			raise Refused(TOO_LARGE)
		if entry.size < self.cutoff:
			return self._mini_read(entry)
		data = self._chain_bytes(entry.start, -(-entry.size // self.ss))
		if len(data) < entry.size:
			raise Refused(FAILED)
		return data[:entry.size]

	# --- the tables -------------------------------------------------------------------------------------------------

	def _fat(self, h: bytes, n_fat: int, first_difat: int, n_difat: int) -> array:
		places = [s for s in struct.unpack_from("<109I", h, 76) if s < MAX_REGULAR]
		per = self.ss // 4 - 1
		at, seen = first_difat, set()
		while at not in (END, FREE) and len(places) < n_fat:
			if len(seen) >= n_difat or at >= self.sectors or at in seen:  # a DIFAT sector met twice is a loop
				raise Refused(FAILED)
			seen.add(at)
			block = self._ints(self._sector(at))
			places += [s for s in block[:per] if s < MAX_REGULAR]
			at = block[per]
		places = places[:n_fat]
		if len(places) < n_fat or len(set(places)) != n_fat:  # every FAT sector once
			raise Refused(FAILED)
		fat = array("I")
		for s in places:
			fat.extend(self._ints(self._sector(s)))
		del fat[self.sectors:]  # entries past the file's own sectors name nothing
		return fat

	def _directory(self, first: int) -> list[Entry]:
		raw = self._chain_bytes(first, MAX_DIR_ENTRIES * 128 // self.ss)
		entries = []
		for at in range(0, len(raw) - 127, 128):
			length, kind = struct.unpack_from("<HB", raw, at + 64)
			start, size = struct.unpack_from("<IQ", raw, at + 116)
			if self.major == 3:
				size &= 0xFFFFFFFF  # version 3 leaves the high half undefined
			if kind not in (STORAGE, STREAM, ROOT) or not 2 <= length <= 64:
				if not entries:
					raise Refused(FAILED)  # the first entry is the root
				continue
			name = raw[at:at + length - 2].decode("utf-16-le", "replace")
			entries.append(Entry(name, kind, start, size))
		if not entries or entries[0].kind != ROOT:
			raise Refused(FAILED)
		return entries

	def _chain(self, start: int, most: int) -> array:
		"""The sectors of a chain; refused when it loops, leaves the file or runs past ``most``."""
		out, at = array("I"), start
		limit = min(most, len(self.fat))
		while at != END:
			if at >= len(self.fat) or at >= self.sectors or len(out) >= limit:
				raise Refused(FAILED)
			out.append(at)
			at = self.fat[at]
		return out

	def _chain_bytes(self, start: int, most: int) -> bytes:
		return b"".join(self._sector(s) for s in self._chain(start, most))

	def _mini_read(self, entry: Entry) -> bytes:
		"""A small stream lives in the root's mini stream, in 64-byte sectors chained by the mini FAT."""
		if self._mini_sectors is None:
			root = self.entries[0]
			self._mini_sectors = self._chain(root.start, -(-root.size // self.ss)) if root.size else array("I")
		out, at, steps = [], entry.start, 0
		need = -(-entry.size // self.mss)
		while at != END and steps < need:
			steps += 1
			if at >= len(self.minifat):
				raise Refused(FAILED)
			offset = at * self.mss
			index, within = divmod(offset, self.ss)
			if index >= len(self._mini_sectors):
				raise Refused(FAILED)
			out.append(self._at((self._mini_sectors[index] + 1) * self.ss + within, self.mss))
			at = self.minifat[at]
		data = b"".join(out)
		if len(data) < entry.size:
			raise Refused(FAILED)
		return data[:entry.size]

	# --- bytes ------------------------------------------------------------------------------------------------------

	def _sector(self, n: int) -> bytes:
		if n >= self.sectors:
			raise Refused(FAILED)
		offset = (n + 1) * self.ss
		return self._at(offset, min(self.ss, self.size - offset)).ljust(self.ss, b"\0")

	def _at(self, offset: int, length: int) -> bytes:
		if offset + length > self.size:
			raise Refused(FAILED)
		self.fh.seek(offset)
		data = self.fh.read(length)
		if len(data) != length:
			raise Refused(FAILED)
		return data

	@staticmethod
	def _ints(data: bytes) -> array:
		out = array("I")
		out.frombytes(data[:len(data) // 4 * 4])
		if out.itemsize != 4:
			raise Refused(FAILED)
		return out if struct.pack("=I", 1) == struct.pack("<I", 1) else _swapped(out)


def _swapped(values: array) -> array:
	values.byteswap()  # a big-endian host: the file's numbers are little-endian
	return values


def open_compound(fh) -> Compound:
	fh.seek(0, 2)
	size = fh.tell()
	return Compound(fh, size)
