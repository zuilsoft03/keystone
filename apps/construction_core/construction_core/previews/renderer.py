"""The thumbs worker's side of the renderer (deploy/renderer/server.py): send the bytes, take the WebP back, and check
it before anything stores it. The renderer has no network: it is reached through a Unix socket on a volume only the
two containers share (``cc_renderer_socket``, default ``/run/renderer/render.sock``); a test points
``cc_renderer_host`` and ``cc_renderer_port`` at a fake one over TCP. A renderer that is down or busy is a passing
failure, retried with backoff (§15.3)."""

import json
import os
import socket
import stat
import struct
from dataclasses import dataclass, field

import frappe
from frappe.utils import cint, flt

MAGIC = b"CCR1"
MAX_ANSWER = 2 * 1024 * 1024  # a 400 px WebP is tens of KB
CHUNK = 1024 * 1024


class Unavailable(Exception):
	"""The renderer could not run the job now: try again later."""


@dataclass
class Drawn:
	ok: bool
	reason: str | None = None
	width: int = 0
	height: int = 0
	webp: bytes = b""
	meta: dict = field(default_factory=dict)


def render(kind: str, content: bytes, px: int) -> Drawn:
	"""One job. Raises Unavailable for a passing failure; any answer of the renderer is a Drawn."""
	timeout = flt(frappe.conf.get("cc_renderer_timeout")) or 120.0
	header = json.dumps({"kind": kind, "px": px}).encode()
	try:
		with _connect() as s:
			s.settimeout(timeout)
			s.sendall(MAGIC + struct.pack("!I", len(header)) + header + struct.pack("!Q", len(content)))
			view = memoryview(content)
			for i in range(0, len(content), CHUNK):
				s.sendall(view[i:i + CHUNK])
			answer = _receive(s)
	except OSError as e:
		raise Unavailable(type(e).__name__) from None
	return _checked(answer)


def _connect() -> socket.socket:
	host = frappe.conf.get("cc_renderer_host")
	if host:
		return socket.create_connection((host, cint(frappe.conf.get("cc_renderer_port")) or 7300), timeout=10)
	# The renderer owns the socket's folder, so a compromised one could put a link there in its place: the path is
	# opened without following a link, must be a socket, and is connected to through that very handle (no race).
	path = frappe.conf.get("cc_renderer_socket") or "/run/renderer/render.sock"
	handle = os.open(path, os.O_PATH | os.O_NOFOLLOW)
	try:
		if not stat.S_ISSOCK(os.fstat(handle).st_mode):
			raise OSError("the renderer's address is not a socket")
		s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		s.settimeout(10)
		try:
			s.connect(f"/proc/self/fd/{handle}")
		except OSError:
			s.close()
			raise
		return s
	finally:
		os.close(handle)


def _receive(s) -> tuple[dict, bytes]:
	def exactly(n):
		out = bytearray()
		while len(out) < n:
			got = s.recv(min(65536, n - len(out)))
			if not got:
				raise ConnectionError("closed")
			out += got
		return bytes(out)

	if exactly(4) != MAGIC:
		raise ConnectionError("protocol")
	(size,) = struct.unpack("!I", exactly(4))
	if size > 65536:
		raise ConnectionError("header")
	header = json.loads(exactly(size))
	(body,) = struct.unpack("!I", exactly(4))
	if body > MAX_ANSWER:
		raise ConnectionError("answer")
	return header, exactly(body)


def _checked(answer: tuple[dict, bytes]) -> Drawn:
	header, body = answer
	if not isinstance(header, dict):
		raise Unavailable("answer")
	if not header.get("ok"):
		if not header.get("fixed"):
			raise Unavailable(str(header.get("reason") or "busy"))
		return Drawn(False, reason=str(header.get("reason") or "failed"), meta=_meta(header.get("meta")))
	size = webp_size(body)
	if not size:
		return Drawn(False, reason="failed")
	return Drawn(True, width=size[0], height=size[1], webp=body, meta=_meta(header.get("meta")))


def _meta(value) -> dict:
	"""Only short strings and flags survive: the card shows them as text (IFC's schema and app, a PDF's lock)."""
	if not isinstance(value, dict):
		return {}
	out = {}
	for key in ("schema", "app", "encrypted"):
		v = value.get(key)
		if isinstance(v, bool):
			out[key] = v
		elif isinstance(v, str) and v:
			out[key] = "".join(c for c in v if c.isprintable())[:80]
	return out


def webp_size(data: bytes, most: int = 512) -> tuple[int, int] | None:
	"""(width, height) of a still WebP of at most ``most`` px, read from its own chunks without decoding it: a lossy
	frame (VP8), a lossless one (VP8L), or an extended header (VP8X) with only an alpha chunk (ALPH) and one frame, the
	frame the size the header says. Anything else (animation, metadata, ICC, a trailing chunk) is refused."""
	if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP" or struct.unpack_from("<I", data, 4)[0] + 8 != len(data):
		return None
	chunks, at = [], 12
	while at + 8 <= len(data) and len(chunks) < 4:
		kind, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
		end = at + 8 + size + (size & 1)
		if end > len(data):
			return None
		chunks.append((kind, data[at + 8:at + 8 + size]))
		at = end
	if at != len(data):
		return None
	kinds = [k for k, _ in chunks]
	if kinds in ([b"VP8 "], [b"VP8L"]):
		size = _frame_size(*chunks[0])
	elif kinds in ([b"VP8X", b"VP8 "], [b"VP8X", b"ALPH", b"VP8 "], [b"VP8X", b"VP8L"]):
		head = chunks[0][1]
		if len(head) != 10 or head[0] & ~0x10:  # only the alpha flag may be set
			return None
		canvas = (1 + int.from_bytes(head[4:7], "little"), 1 + int.from_bytes(head[7:10], "little"))
		size = _frame_size(*chunks[-1])
		size = size if size == canvas else None
	else:
		return None
	return size if size and 0 < size[0] <= most and 0 < size[1] <= most else None


def _frame_size(kind: bytes, frame: bytes) -> tuple[int, int] | None:
	if kind == b"VP8 " and len(frame) >= 10 and frame[3:6] == b"\x9d\x01\x2a":
		return struct.unpack_from("<H", frame, 6)[0] & 0x3FFF, struct.unpack_from("<H", frame, 8)[0] & 0x3FFF
	if kind == b"VP8L" and len(frame) >= 5 and frame[0] == 0x2F:
		bits = struct.unpack_from("<I", frame, 1)[0]
		return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
	return None
