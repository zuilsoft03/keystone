"""The thumbs job (P3-75, design §15.1, §15.3): one Preview Image row made, on the ``thumbs`` queue, one at a time.

The order: the bytes are read and checked against the row's key, and their sha256 taken; a row of the same bytes that
is already final is copied; a team file not scanned yet goes to clamd first (it fails closed: clamd down is a passing
failure); the reader is chosen by magic bytes; Office files go to the Document Server, everything else to the renderer
(bytes in, a WebP out, checked here); a PDF that PDFium cannot read is offered to the Document Server; the row and the
chat cards of its file take the answer. Nothing here fails the upload, send or save that asked for the preview.
"""

import hashlib
import os

import frappe
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import cint, now_datetime

from construction_core.approvals import frozen
from construction_core.previews import DOCTYPE, PX, QUEUE, office, renderer, store
from construction_core.previews.readers import common, dispatch
from construction_core.previews.sources import COPY, Target

MAX_SOURCE = 260 * 1024**2  # the renderer's input limit
SWEEP_BATCH = 50
NOT_YET = (dispatch.SKP,)  # SKP's picture after G5 on two real files: the placeholder until then
READ = frozenset({"pdf", "jpg", "jpeg", "png", "webp", "dwg", "dxf", "rvt", "rfa", "ifc", *dispatch.OFFICE_TYPES})


def previewable(ext: str | None) -> bool:
	"""Whether a file of this type gets a job (its bytes still decide the reader)."""
	return (ext or "").lower() in READ


def request(target: Target, *, after_commit: bool = True) -> frappe._dict | None:
	"""The target's row, made when missing, and its job queued when it needs one. In a request that writes (a send, a
	save) the job is queued after the commit."""
	if not target.server:
		return store.row_of(target)  # made by its own writer (a board's snapshot), never by a job
	row = store.ensure(target)
	if row and store.wants_work(row):
		enqueue(row.name, after_commit=after_commit)
	return row


def ask(target: Target) -> None:
	"""From a read (GET): no row is written here; the job makes the row itself. Deduplicated per source and key."""
	if not target.server:
		return
	_queue("construction_core.previews.jobs.ensure_and_make", f"cc-preview-ensure|{target.source_type}|"
		f"{target.source_name}|{target.key}", after_commit=False, target=target.__dict__)


def enqueue(preview: str, *, after_commit: bool = True) -> None:
	_queue("construction_core.previews.jobs.make", f"cc-preview|{preview}", after_commit=after_commit, preview=preview)


def ensure_and_make(target: dict) -> None:
	frappe.set_user("Administrator")
	row = store.ensure(Target(**target))
	if row and store.wants_work(row):
		make(row.name)


def make(preview: str) -> None:
	"""The job. Every outcome is written to the row; an unexpected error is logged and leaves the row to the sweep."""
	frappe.set_user("Administrator")
	row = frappe.db.get_value(DOCTYPE, preview, store.ROW_FIELDS, as_dict=True)
	if not row or row.source_type not in ("File", COPY) or not store.wants_work(row):
		return  # only a File's and a frozen copy's bytes are drawn here
	try:
		Job(row).run()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="construction_core: preview job failed", message=f"preview={preview}")
		store.mark_retry(row)


def retry_due() -> int:
	"""Every five minutes: pending rows whose retry is due (and rows a migration armed) are queued again."""
	due = {"state": "pending", "source_type": ["in", ("File", COPY)]}
	rows = frappe.get_all(DOCTYPE, filters={**due, "retry_after": ["<=", now_datetime()]}, pluck="name",
		limit=SWEEP_BATCH, order_by="retry_after asc")
	rows += frappe.get_all(DOCTYPE, filters={**due, "retry_after": ["is", "not set"]}, pluck="name",
		limit=SWEEP_BATCH, order_by="modified asc")
	for name in dict.fromkeys(rows):
		enqueue(name, after_commit=False)
	return len(rows)


class Job:
	def __init__(self, row):
		self.row = row
		self.kind = None

	def run(self) -> None:
		path = self._path()
		if not path:
			return store.mark_final(self.row, "failed", common.FAILED)
		if os.path.getsize(path) > MAX_SOURCE:
			return store.mark_final(self.row, "failed", common.TOO_LARGE)
		content = self._bytes(path)
		if content is None:
			return store.mark_final(self.row, "failed", common.FAILED)
		sha256 = hashlib.sha256(content).hexdigest()
		self.row.sha256 = sha256
		frappe.db.set_value(DOCTYPE, self.row.name, "sha256", sha256, update_modified=False)
		twin = store.twin_values(sha256)
		if twin:
			return self._copy(twin)
		self.kind = dispatch.sniff(content[:4096], self.row.ext)
		if self.kind is None or self.kind in NOT_YET or (self.kind == dispatch.OFFICE and not office.configured()):
			return store.mark_final(self.row, "skipped", common.NOT_SUPPORTED, self.kind)
		if not self.row.scanned and not store.scanned_before(sha256) and not self._scan(content):
			return
		if self.kind == dispatch.OFFICE:
			return self._through_office(sha256)
		self._through_renderer(content, sha256)

	def _through_renderer(self, content: bytes, sha256: str) -> None:
		data = content[:64 * 1024] if self.kind == dispatch.IFC else content
		try:
			drawn = renderer.render(self.kind, data, PX)
		except renderer.Unavailable:
			return store.mark_retry(self.row)
		if not drawn.ok and self.kind == dispatch.PDF and drawn.reason == common.FAILED and office.configured():
			return self._through_office(sha256, fallback=True)  # PDFium could not read it: the Document Server may
		self._answer(drawn)

	def _through_office(self, sha256: str, fallback: bool = False) -> None:
		"""The Document Server's PNG of the first page, drawn again in the renderer like any picture."""
		ext = "pdf" if fallback else (self.row.ext or "").lower()
		try:
			png = office.convert(self.row.source_name, ext, sha256)
			drawn = renderer.render(dispatch.PAGE, png, PX)
		except office.Refusal as e:
			return store.mark_final(self.row, "failed", e.reason, self.kind)
		except (office.Unavailable, renderer.Unavailable):
			if fallback:
				return store.mark_final(self.row, "failed", common.FAILED, self.kind)
			return store.mark_retry(self.row)
		self._answer(drawn)

	def _answer(self, drawn) -> None:
		if drawn.ok:
			return store.mark_ready(self.row, self.kind, drawn.width, drawn.height, drawn.webp, drawn.meta)
		state = "skipped" if drawn.reason == common.NOT_SUPPORTED else "failed"
		store.mark_final(self.row, state, drawn.reason if drawn.reason in common.REASONS else common.FAILED, self.kind,
			drawn.meta)

	def _copy(self, twin: dict) -> None:
		store.finish(self.row, **twin)

	def _path(self) -> str | None:
		if self.row.source_type == COPY:  # P3-77: a frozen copy, named by its SHA-256
			path = frozen.path_of(self.row.source_name)
			return path if path and os.path.isfile(path) else None
		if self.row.source_type != "File" or not frappe.db.exists("File", self.row.source_name):
			return None
		path = frappe.get_doc("File", self.row.source_name).get_full_path()
		return path if path and os.path.isfile(path) else None

	def _bytes(self, path: str) -> bytes | None:
		"""The stored bytes as they are (File.get_content decodes text, and a re-encode would change them), only when
		they are still the ones the row was made for."""
		try:
			with open(path, "rb") as fh:
				content = fh.read()
		except OSError:
			return None
		key = hashlib.sha256(content).hexdigest() if self.row.source_type == COPY else get_content_hash(content)
		if not content or key != self.row.source_key:
			return None
		return content

	def _scan(self, content: bytes) -> bool:
		"""A team file is scanned before any reader sees it (§15.3). Infected or unscannable: no preview, ever; clamd
		down: try again later. Returns whether the job may go on."""
		from construction_core import client_files

		if len(content) > client_files.MODEL_MAX:
			store.mark_final(self.row, "failed", common.TOO_LARGE)
			return False
		try:
			client_files.scan(content, sent=False, budget=client_files.BACKGROUND_SCAN_SECONDS)
		except client_files.ScanUnavailable:
			frappe.clear_last_message()
			store.mark_retry(self.row)
			return False
		except frappe.ValidationError:
			frappe.clear_last_message()
			store.mark_final(self.row, "failed", common.FAILED)
			return False
		store.mark_scanned(self.row.sha256)
		return True


def _queue(method: str, job_id: str, *, after_commit: bool, **kwargs) -> None:
	"""frappe.enqueue on the thumbs queue. Tests keep the jobs in a list (``frappe.flags.cc_previews_queued``), or run
	them at once with ``frappe.flags.cc_previews_sync``, so a test never leaves work for the stack's worker."""
	if frappe.flags.cc_previews_sync:
		frappe.get_attr(method)(**kwargs)
		return
	if frappe.in_test:
		frappe.flags.cc_previews_queued = [*(frappe.flags.cc_previews_queued or []), (method, kwargs)]
		return
	frappe.enqueue(method, queue=QUEUE, job_id=job_id, deduplicate=True, enqueue_after_commit=after_commit,
		timeout=cint(frappe.conf.get("cc_preview_job_timeout")) or 600, **kwargs)
