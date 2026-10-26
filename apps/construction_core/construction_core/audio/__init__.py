"""Voice notes' audio check (P3-67; design §3.6, SEC-16; D-364): our own small readers for the three containers the
recorder makes, in its order: MP4 (AAC), Ogg (Opus) and WebM (Opus).

``read`` walks a file's headers and indexes only, bounded in items, depth and time (``bounds``), and answers what the
file is: its container, codec, the type it is served as, and its length as the file itself states it, never the
browser's. ``check`` turns a refusal into the words the sender sees. The extension a voice note is stored with comes
from ``sniff`` (its first bytes), so the existing private file path serves it with the detected audio type.
"""

from dataclasses import dataclass

from construction_core.audio import mp4, ogg, webm
from construction_core.audio.bounds import Budget, Refused

MAX_BYTES = 10 * 1024 * 1024  # design §3.6
MAX_SECONDS = 300.0
READERS = {"m4a": mp4.read, "ogg": ogg.read, "weba": webm.read}
MIME = {"m4a": "audio/mp4", "ogg": "audio/ogg", "weba": "audio/webm"}  # Python's mimetypes names these the same
CONTAINER = {"m4a": "mp4", "ogg": "ogg", "weba": "webm"}


@dataclass(frozen=True)
class Voice:
	ext: str
	container: str
	codec: str  # aac | opus
	mime: str
	length: float  # seconds


def sniff(content) -> str | None:
	"""The extension a recording is stored as, from its first bytes; None for anything else."""
	head = bytes(content[:12])
	if head[4:8] == b"ftyp":
		return "m4a"
	if head.startswith(b"OggS"):
		return "ogg"
	if head.startswith(b"\x1a\x45\xdf\xa3"):
		return "weba"
	return None


def read(ext: str, content, budget: Budget | None = None) -> Voice:
	"""The voice note's facts, or Refused. The size is checked before any byte is parsed."""
	if ext not in READERS:
		raise Refused("not_valid")
	if len(content) > MAX_BYTES:
		raise Refused("too_large")
	if sniff(content) != ext:
		raise Refused("not_valid")
	codec, seconds = READERS[ext](memoryview(content), budget or Budget())
	if seconds <= 0:
		raise Refused("not_valid")
	if seconds > MAX_SECONDS:
		raise Refused("too_long")
	return Voice(ext, CONTAINER[ext], codec, MIME[ext], round(seconds, 3))


def check(ext: str, content) -> Voice:
	"""``read`` with the refusal in the sender's words (frappe.throw)."""
	import frappe
	from frappe import _

	try:
		return read(ext, content)
	except Refused as e:
		words = {
			"too_large": _("A voice note can be at most 10 MB."),
			"too_long": _("A voice note can be at most 5 minutes long."),
			"video": _("A voice note can carry sound only."),
			"tracks": _("A voice note can carry one sound track only."),
			"codec": _("This recording's format cannot be sent. Record it again."),
			"unseekable": _("This recording cannot be played back properly. Record it again."),
			"too_complex": _("This recording is too complex to check, so it was not sent."),
		}
		frappe.throw(words.get(e.reason) or _("This recording could not be read. Record it again."))
