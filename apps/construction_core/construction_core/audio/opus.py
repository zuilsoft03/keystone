"""How long an Opus packet plays, from its TOC byte (RFC 6716 §3.1): the readers' lower bound from the packets
themselves, which no stated time (a granule, a timecode, a scale) can shorten.
"""

from construction_core.audio.bounds import Refused

RATE = 48_000
SILK, HYBRID, CELT = (480, 960, 1920, 2880), (480, 960), (120, 240, 480, 960)  # samples a frame, at 48 kHz
MAX_PACKET = 5760  # 120 ms: the most one packet may hold (RFC 6716 §3.2.5)


def needs_count(toc: int) -> bool:
	"""Code 3 packets carry their frame count in a second byte."""
	return toc & 3 == 3


def samples(toc: int, count: int | None = None) -> int:
	"""The samples one packet plays. ``count``: the packet's second byte, for a code 3 packet."""
	config = toc >> 3
	size = SILK[config % 4] if config < 12 else HYBRID[config % 2] if config < 16 else CELT[config % 4]
	code = toc & 3
	if code == 3:
		if count is None or not count & 0x3F:
			raise Refused("not_valid")
		frames = count & 0x3F
	else:
		frames = 1 if code == 0 else 2
	if frames * size > MAX_PACKET:
		raise Refused("not_valid")
	return frames * size


def channels_ok(head: bytes) -> bool:
	"""An OpusHead (RFC 7845 §5.1), as Ogg's first packet or WebM's CodecPrivate: version 1 (major 0), mono or
	stereo."""
	return len(head) >= 19 and head[:8] == b"OpusHead" and head[8] >> 4 == 0 and 1 <= head[9] <= 2

