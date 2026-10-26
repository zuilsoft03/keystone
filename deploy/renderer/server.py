"""The renderer (P3-75; design §15.1, D-416): bytes in, a WebP preview out, for the thumbs worker only.

It runs in its own container with no network at all (``network_mode: none``): the thumbs worker reaches it through a
Unix socket on a small tmpfs volume that only the two of them mount. The container has no site data, a read-only
filesystem, every capability dropped, no new privileges, a non-root user, an init that reaps orphans, pids, memory and
CPU limits and a tmpfs for scratch (deploy/compose.yml). Every job runs in a ``python -I`` child (child.py) that sets
its own limits before it reads anything, cannot start a process and cannot be read by another process; a wall-clock
timer kills it. After each job every process the job may have left is killed and the scratch tmpfs is emptied. The
server itself never parses a file, and is not readable by its children either (no core dumps, not dumpable).

The protocol, standard library only (the shape of clamd's INSTREAM):

    request:  b"CCR1" | !I header length | header JSON {"kind", "px"} | !Q payload length | payload
    answer:   b"CCR1" | !I header length | header JSON {"ok", "w", "h", "meta"} or {"ok": false, "reason", "fixed"}
              | !I body length | WebP

A busy renderer, a full scratch disk, or a child the container (not its own limits) killed say ``"fixed": false``
(try again later); a reader's refusal, a limit or the clock are ``"fixed": true`` (stored, never retried, §15.3).
"""

import ctypes
import errno
import json
import os
import resource
import shutil
import signal
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time

MAGIC = b"CCR1"
SOCKET = os.environ.get("RENDER_SOCKET", "/run/renderer/render.sock")
JOBS = int(os.environ.get("RENDER_JOBS", "1"))
MAX_INPUT = int(os.environ.get("RENDER_MAX_BYTES", str(260 * 1024**2)))
MEMORY = int(os.environ.get("RENDER_CHILD_MEMORY", str(1024**3)))  # RLIMIT_AS of a child
MAX_BODY = 2 * 1024**2  # the worker's own limit on an answer (previews/renderer.py MAX_ANSWER)
MAX_OUTPUT = MAX_BODY + 64 * 1024  # the child's answer file: header and body (child.py's RLIMIT_FSIZE)
PX_RANGE = (64, 512)
# kind: (CPU seconds, wall seconds) for one child
LIMITS = {"image": (20, 30), "page": (20, 30), "pdf": (30, 45), "dwg": (10, 15), "dxf": (30, 45), "rvt": (10, 15),
	"ifc": (5, 10)}
CHUNK = 1024 * 1024
SLOTS = threading.BoundedSemaphore(JOBS)
ACTIVE, ACTIVE_LOCK = set(), threading.Lock()  # the pids of children running now
TOO_LARGE, FAILED, BUSY = "too_large", "failed", "busy"
PR_SET_DUMPABLE = 4


class Handler(socketserver.StreamRequestHandler):
	timeout = 60  # a client that stops sending is dropped

	def handle(self):
		try:
			kind, px, length = self._request()
		except (ValueError, TypeError, AttributeError, OSError, RecursionError, struct.error):
			return self._answer({"ok": False, "reason": FAILED, "fixed": True})
		if not SLOTS.acquire(blocking=False):
			self._drain(length)
			return self._answer({"ok": False, "reason": BUSY, "fixed": False})
		try:
			header, body = Job(kind, px).run(self.rfile, length)
		finally:
			SLOTS.release()
			clean_up()
		self._answer(header, body)

	def _request(self) -> tuple[str, int, int]:
		if self.rfile.read(4) != MAGIC:
			raise ValueError("protocol")
		(size,) = struct.unpack("!I", self.rfile.read(4))
		if size > 1024:
			raise ValueError("header")
		header = json.loads(self.rfile.read(size))
		if not isinstance(header, dict) or not isinstance(header.get("kind"), str) or type(header.get("px")) is not int:
			raise ValueError("header")
		kind, px = header["kind"], header["px"]
		(length,) = struct.unpack("!Q", self.rfile.read(8))
		if kind not in LIMITS or not PX_RANGE[0] <= px <= PX_RANGE[1] or length > MAX_INPUT:
			raise ValueError("request")
		return kind, px, length

	def _drain(self, length: int):
		while length > 0:
			got = self.rfile.read(min(CHUNK, length))
			if not got:
				return
			length -= len(got)

	def _answer(self, header: dict, body: bytes = b""):
		raw = json.dumps(header, separators=(",", ":")).encode()
		try:
			self.wfile.write(MAGIC + struct.pack("!I", len(raw)) + raw + struct.pack("!I", len(body)) + body)
		except OSError:
			pass


class Job:
	"""One child on one input, with its wall clock, its peak memory and one log line."""

	def __init__(self, kind: str, px: int):
		self.kind, self.px = kind, px
		self.cpu, self.wall = LIMITS[kind]

	def run(self, stream, length: int) -> tuple[dict, bytes]:
		started = time.monotonic()
		status, usage = 0, None
		try:
			with tempfile.TemporaryFile(dir="/tmp") as source, tempfile.TemporaryFile(dir="/tmp") as answer:
				if not self._receive(stream, source, length):
					return {"ok": False, "reason": FAILED, "fixed": True}, b""
				source.seek(0)
				status, usage, killed = self._child(source, answer)
				header, body = self._read(answer, status, killed, usage)
		except OSError as e:
			if e.errno not in (errno.ENOSPC, errno.EDQUOT, errno.EMFILE):
				raise
			header, body = {"ok": False, "reason": BUSY, "fixed": False}, b""  # scratch full: try again later
		self._log(length, started, usage, header, status)
		return header, body

	def _receive(self, stream, target, length: int) -> bool:
		left = length
		while left > 0:
			got = stream.read(min(CHUNK, left))
			if not got:
				return False
			target.write(got)
			left -= len(got)
		target.flush()
		return True

	def _child(self, source, answer):
		proc = subprocess.Popen([sys.executable, "-I", "/opt/renderer/child.py", self.kind, str(self.px), str(self.cpu),
			str(MEMORY), str(MAX_OUTPUT)], stdin=source, stdout=answer, stderr=subprocess.DEVNULL, close_fds=True,
			start_new_session=True)
		with ACTIVE_LOCK:
			ACTIVE.add(proc.pid)
		killed = threading.Event()

		def kill():
			killed.set()
			try:
				os.killpg(proc.pid, signal.SIGKILL)
			except ProcessLookupError:
				pass

		timer = threading.Timer(self.wall, kill)
		timer.start()
		try:
			_pid, status, usage = os.wait4(proc.pid, 0)
		finally:
			timer.cancel()
			with ACTIVE_LOCK:
				ACTIVE.discard(proc.pid)
		proc.returncode = 0  # reaped here: Popen must not wait again
		return status, usage, killed.is_set()

	def _read(self, answer, status: int, killed: bool, usage) -> tuple[dict, bytes]:
		verdict = self._ended(status, killed, usage)
		if verdict:
			return verdict, b""
		answer.seek(0)
		raw = answer.read(MAX_OUTPUT + 1)
		try:
			(size,) = struct.unpack_from("!I", raw, 0)
			header = json.loads(raw[4:4 + size])
			(body_size,) = struct.unpack_from("!I", raw, 4 + size)
			body = raw[8 + size:8 + size + body_size]
		except (ValueError, struct.error):
			return {"ok": False, "reason": FAILED, "fixed": True}, b""
		if (not isinstance(header, dict) or len(body) != body_size or body_size > MAX_BODY
				or (header.get("ok") and not body)):
			return {"ok": False, "reason": FAILED, "fixed": True}, b""
		header["fixed"] = True
		return header, body

	def _ended(self, status: int, killed: bool, usage) -> dict | None:
		"""How a child that did not finish ended: its own limits or the clock (fixed), the container's memory (passing:
		another job may have used it), or a crash (fixed). None when it exited normally."""
		cpu = getattr(usage, "ru_utime", 0) + getattr(usage, "ru_stime", 0)
		peak = getattr(usage, "ru_maxrss", 0) * 1024
		exited = os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
		sig = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None
		if killed or sig in (signal.SIGXCPU, signal.SIGXFSZ) or (sig == signal.SIGKILL and cpu >= self.cpu):
			return {"ok": False, "reason": TOO_LARGE, "fixed": True, "killed": True}
		if sig == signal.SIGKILL:  # neither the clock nor its CPU limit: the container's memory ran out
			return {"ok": False, "reason": BUSY, "fixed": False, "killed": True}
		if not exited and MEMORY and peak >= MEMORY * 0.9:  # a native library at its address-space limit aborts
			return {"ok": False, "reason": TOO_LARGE, "fixed": True, "killed": True}
		if not exited:
			return {"ok": False, "reason": FAILED, "fixed": True, "killed": True}  # a crash: never retried
		return None

	def _log(self, length: int, started: float, usage, header: dict, status: int):
		"""One line per job, never a byte of the file: what it was, how long, how much memory, how it ended."""
		print(json.dumps({"kind": self.kind, "bytes": length, "ms": round((time.monotonic() - started) * 1000),
			"peak_kib": getattr(usage, "ru_maxrss", 0),
			"cpu_s": round(getattr(usage, "ru_utime", 0) + getattr(usage, "ru_stime", 0), 2),
			"ok": header.get("ok"), "reason": header.get("reason"), "killed": header.get("killed", False),
			"signal": os.WTERMSIG(status) if os.WIFSIGNALED(status) else None}), file=sys.stderr, flush=True)


def clean_up():
	"""After a job: any process the job may have left (an orphan, or one in a session of its own) is killed, and when
	no other job runs the scratch tmpfs is emptied. Spared: the init (pid 1), this server, the children of jobs still
	running, and processes started from outside (docker exec: parent pid 0)."""
	me = os.getpid()
	with ACTIVE_LOCK:
		spared, idle = {1, me, *ACTIVE}, not ACTIVE
	for entry in os.listdir("/proc"):
		if not entry.isdigit() or int(entry) in spared:
			continue
		try:
			with open(f"/proc/{entry}/stat", "rb") as fh:
				parent = int(fh.read().rsplit(b")", 1)[1].split()[1])
		except (OSError, ValueError, IndexError):
			continue
		if parent in (1, me):
			try:
				os.kill(int(entry), signal.SIGKILL)
			except (ProcessLookupError, PermissionError):
				pass
	if idle:
		for entry in os.listdir("/tmp"):
			path = os.path.join("/tmp", entry)
			try:
				shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) else os.remove(path)
			except OSError:
				pass


def not_dumpable():
	"""No process of the same user may read this one's memory or open files (/proc/<pid>/fd, mem, environ)."""
	if ctypes.CDLL(None, use_errno=True).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
		raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE)")


class Server(socketserver.ThreadingUnixStreamServer):
	daemon_threads = True
	request_queue_size = 16


def main():
	resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
	not_dumpable()
	if os.path.exists(SOCKET):
		os.remove(SOCKET)  # left by a container that stopped
	with Server(SOCKET, Handler) as server:
		os.chmod(SOCKET, 0o666)  # the thumbs worker runs as another user; the volume is shared with it alone
		print(json.dumps({"listening": SOCKET, "jobs": JOBS, "child_memory": MEMORY}), file=sys.stderr, flush=True)
		server.serve_forever()


if __name__ == "__main__":
	main()
