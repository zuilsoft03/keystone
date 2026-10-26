"""Large files scanned after the request (P3-75; design §15.4, QP-3; D-417).

clamd takes about 10 s for 250 MB (G7), more for an archive-rich file, and a request has 120 s in all: a file above
``client_files.SCAN_IN_REQUEST`` is held and scanned by a job on the thumbs queue (its worker reaches clamd).

- **A client's Files send** is held as a **Scan Hold** row (uploader, project, folder, size, sha256, the held bytes'
  name, state, tries) with its bytes outside the site's files. Nobody can open, share or send it. Clean: it becomes
  the client's File, as an ordinary send would, and the row goes. A threat, a file clamd cannot fully check, or a
  scan that could not run in MAX_TRIES tries: the bytes go and the row stays ``Refused`` with its reason, which the
  client's checking list shows for a week. The row is in the database, so a cache restart loses nothing; it counts in
  the project's daily cap from its arrival until it is a File.
- **A chat upload** waits as its Pending Discuss Attachment marked ``checking`` (discuss.parts.attachments), with the
  same tries and the same reasons.

One retry policy for both: clamd down is tried again by the five-minute sweep, at most MAX_TRIES times in all.
"""

import hashlib
import os
import time

import frappe
from frappe.utils import add_to_date, add_days, get_site_path, now_datetime

from construction_core import client_files

DOCTYPE = "Scan Hold"
HOLD = "cc_scan_hold"  # beside the chat's staging folder, outside private/files
MAX_TRIES = 12  # with a try every five minutes: an hour of clamd down
RETRY_MINUTES = 5
LOST_MINUTES = 15  # a first scan not run by then was lost; it is queued again
THREAT, COULD_NOT_CHECK, NOT_STORED = "threat", "could_not_check", "not_stored"
KEEP_REFUSED_DAYS = 7
FIELDS = ["name", "uploader", "project", "folder", "file_name", "ext", "size", "sha256", "staged", "state", "reason",
	"tries"]


def hold(project: str, display: str, ext: str, content: bytes) -> dict:
	"""Keep a checked file that is too large to scan in the request, and queue its scan. What the client sees: its name
	and "Checking…"."""
	from construction_core.workspace import client_folders

	staged = f"{frappe.generate_hash(length=24)}.{ext}"
	path = held_path(staged)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "xb") as fh:
		fh.write(content)
	frappe.db.after_rollback.add(lambda: os.path.exists(path) and os.remove(path))
	row = frappe.get_doc({"doctype": DOCTYPE, "uploader": frappe.session.user, "project": project,
		"folder": client_folders(project)["inbox"], "file_name": display, "ext": ext, "size": len(content),
		"sha256": hashlib.sha256(content).hexdigest(), "staged": staged, "state": "Checking"}).insert(
		ignore_permissions=True)
	queue("construction_core.scan_holds.scan_held", hold=row.name)
	return {"file_name": display, "size": len(content), "shared": False, "checking": True}


def checking(project: str, user: str) -> list:
	"""The user's held sends of this project: name, size, and a reason once refused. Never a path, id or hash."""
	rows = frappe.get_all(DOCTYPE, filters={"project": project, "uploader": user}, fields=["file_name", "size",
		"state", "reason", "creation"], order_by="creation desc", limit=50)
	return [{"file_name": r.file_name, "size": r.size, "checking": r.state == "Checking",
		"reason": r.reason if r.state == "Refused" else None} for r in rows]


def scan_held(hold: str) -> None:
	"""The background scan of a held send. Clean: stored as the client's own send and the row goes. Refused: the bytes
	go, the row keeps the reason. clamd down: tried again by the sweep, MAX_TRIES times in all."""
	from construction_core import portal_api

	row = frappe.db.get_value(DOCTYPE, hold, FIELDS, as_dict=True)
	path = held_path(row.staged) if row else None
	if not row or row.state != "Checking":
		return
	if not path or not os.path.exists(path):
		return refuse(row, NOT_STORED)
	with open(path, "rb") as fh:
		content = fh.read()
	if hashlib.sha256(content).hexdigest() != row.sha256:
		return refuse(row, NOT_STORED)
	verdict = scan(content, row.project)
	if verdict == "later":
		return retry_later(row)
	if verdict:
		return refuse(row, verdict)
	locked = frappe.db.get_value(DOCTYPE, row.name, "state", for_update=True)  # one job stores it, once
	if locked != "Checking":
		return
	if not may_still_send(row):
		return refuse(row, NOT_STORED)
	frappe.set_user(row.uploader)
	try:
		portal_api._store(row.project, row.file_name, content)
	except (frappe.ValidationError, frappe.PermissionError):  # the client left the project, its folder went, ...
		frappe.clear_last_message()
		frappe.set_user("Administrator")
		return refuse(row, NOT_STORED)
	frappe.set_user("Administrator")
	frappe.db.delete(DOCTYPE, row.name)
	frappe.db.after_commit.add(lambda: os.path.exists(path) and os.remove(path))


def may_still_send(row) -> bool:
	"""The send's own checks again, at storing (FIT-19, as the chat's claim does): the uploader still reads the project
	and its portal's Files section is still on."""
	from construction_core import portal
	from construction_core.permissions import client_section_open

	try:
		return bool(portal.can_read_project(row.project, user=row.uploader)) and bool(client_section_open("File",
			row.project))
	except (frappe.DoesNotExistError, frappe.PermissionError):
		frappe.clear_last_message()
		return False


def scan(content: bytes, project: str | None) -> str | None:
	"""None when clean; THREAT or COULD_NOT_CHECK when refused for good; "later" when clamd did not answer."""
	try:
		client_files.scan(content, project=project, budget=client_files.BACKGROUND_SCAN_SECONDS)
	except client_files.ScanUnavailable:
		frappe.clear_last_message()
		return "later"
	except client_files.ScanIncomplete:
		frappe.clear_last_message()
		return COULD_NOT_CHECK
	except frappe.ValidationError:  # client_files.ScanThreat, or any other refusal: never stored
		frappe.clear_last_message()
		return THREAT
	return None


def gives_up(tries) -> bool:
	"""After the MAX_TRIES-th scan that could not run, the file is refused as "could not be checked" (both holds)."""
	return int(tries or 0) + 1 >= MAX_TRIES


def retry_later(row) -> None:
	if gives_up(row.tries):
		return refuse(row, COULD_NOT_CHECK)
	frappe.db.set_value(DOCTYPE, row.name, {"tries": int(row.tries or 0) + 1,
		"next_try": add_to_date(now_datetime(), minutes=RETRY_MINUTES)}, update_modified=False)


def refuse(row, reason: str) -> None:
	path = held_path(row.staged)
	frappe.db.set_value(DOCTYPE, row.name, {"state": "Refused", "reason": reason, "staged": None}, update_modified=False)
	frappe.db.after_commit.add(lambda: path and os.path.exists(path) and os.remove(path))


def rescan_due() -> int:
	"""Every five minutes: holds whose scan could not run are queued again once their next try is due, and so are holds
	whose first job was lost (a queue restart, a killed worker) after LOST_MINUTES; a hold still checking after a day
	is refused, so its bytes go."""
	now = now_datetime()
	for name in frappe.get_all(DOCTYPE, filters={"state": "Checking", "creation": ["<", add_days(now, -1)]},
			pluck="name", limit=50):
		refuse(frappe.db.get_value(DOCTYPE, name, FIELDS, as_dict=True), COULD_NOT_CHECK)
	due = frappe.get_all(DOCTYPE, filters={"state": "Checking", "tries": [">", 0], "next_try": ["<=", now]},
		pluck="name", limit=50)
	lost = frappe.get_all(DOCTYPE, filters={"state": "Checking", "tries": 0,
		"creation": ["<", add_to_date(now, minutes=-LOST_MINUTES)]}, pluck="name", limit=50)
	for name in dict.fromkeys(due + lost):
		queue("construction_core.scan_holds.scan_held", hold=name, after_commit=False)
	return len(set(due + lost))


def sweep() -> int:
	"""Hourly: refused rows older than a week go; held bytes that no Checking row names (older than an hour) go."""
	frappe.db.delete(DOCTYPE, {"state": "Refused", "creation": ["<", add_days(now_datetime(), -KEEP_REFUSED_DAYS)]})
	folder = get_site_path("private", HOLD)
	if not os.path.isdir(folder):
		return 0
	cutoff = time.time() - 3600
	old = [e.name for e in os.scandir(folder) if e.is_file() and e.stat().st_mtime < cutoff]
	named = set(frappe.get_all(DOCTYPE, filters={"staged": ["in", old], "state": "Checking"}, pluck="staged")) if old else set()
	gone = [n for n in old if n not in named]
	for n in gone:
		os.remove(os.path.join(folder, n))
	return len(gone)


def counted(project: str) -> tuple[int, int]:
	"""(files, bytes) of today's holds that are not Files yet, for client_files.check_daily_cap."""
	files, size = frappe.db.sql("""select count(*), coalesce(sum(size), 0) from `tabScan Hold`
		where project = %s and creation >= %s""", (project, frappe.utils.today()))[0]
	return int(files), int(size)


def held_path(staged: str | None) -> str | None:
	if not staged or os.path.basename(staged) != staged or staged.startswith("."):
		return None
	return get_site_path("private", HOLD, staged)


def queue(method: str, *, after_commit: bool = True, **kwargs) -> None:
	"""On the thumbs queue: its worker is the one beside the web server that reaches clamd. Tests keep it in a list."""
	if frappe.in_test:
		frappe.flags.cc_scan_holds = [*(frappe.flags.cc_scan_holds or []), (method, kwargs)]
		return
	job = "|".join(str(v) for v in kwargs.values())
	frappe.enqueue(method, queue="thumbs", timeout=900, enqueue_after_commit=after_commit, deduplicate=True,
		job_id=f"cc-scan|{job}|{int(time.time()) // (RETRY_MINUTES * 60)}", **kwargs)
