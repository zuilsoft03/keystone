"""One preview job, in its own process (design §15.1; the PDF_WALK pattern of client_files.py).

The limits are set first, before any input is read or any reader imported: CPU time (a signal at the limit, a kill
two seconds later), address space, open files, the size of any file written (its answer only), no core dumps, and no
new process at all (a reader cannot start another program, nor leave one behind). Then the process makes itself
undumpable, so no other process of the same user can read its memory or files. Then the job's bytes are read from
stdin (a file on the scratch tmpfs, so readers can seek) and the answer is written to stdout: a length-prefixed JSON
header, then the WebP. Run as ``python -I`` (no environment, no user site, not the script's own folder), so the
readers' folder is added to the path by hand, after the limits.

    python -I child.py <kind> <px> <cpu seconds> <memory bytes, 0 for none> <answer bytes>
"""

import resource
import sys

KIND, PX, CPU, MEMORY, ANSWER = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
resource.setrlimit(resource.RLIMIT_CPU, (CPU, CPU + 2))
if MEMORY:
	resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
resource.setrlimit(resource.RLIMIT_FSIZE, (ANSWER, ANSWER))  # its answer file, and nothing larger
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))  # no fork, no thread of another process: nothing outlives the job

try:  # if the container runs out of memory, the kernel ends a job before the server (raising needs no privilege)
	with open("/proc/self/oom_score_adj", "w") as fh:
		fh.write("1000")
except OSError:
	pass

import ctypes  # noqa: E402

if ctypes.CDLL(None).prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE 0 (after the write above: /proc/self is root's then)
	sys.exit(70)

sys.path.insert(0, "/opt/renderer")

import json  # noqa: E402
import struct  # noqa: E402

from construction_core.previews.readers import common, dispatch  # noqa: E402


def main() -> None:
	body = b""
	try:
		result = dispatch.render(KIND, sys.stdin.buffer, PX)
		header = {"ok": True, "w": result.width, "h": result.height, "meta": result.meta}
		body = result.webp
	except common.Refused as e:
		header = {"ok": False, "reason": e.reason, "meta": e.meta}
	except MemoryError:
		header = {"ok": False, "reason": common.TOO_LARGE, "meta": {}}
	except Exception:
		header = {"ok": False, "reason": common.FAILED, "meta": {}}
	raw = json.dumps(header, separators=(",", ":")).encode()
	out = sys.stdout.buffer
	out.write(struct.pack("!I", len(raw)) + raw + struct.pack("!I", len(body)) + body)
	out.flush()


main()
