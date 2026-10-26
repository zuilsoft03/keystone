"""Design events as System cards (P3-69; design §3.9, §14.2; D-419, D-420).

A short job after the commit (core.events, the short queue) turns three app events into a System message:
``document.published``, ``file.revised`` (files/versions.py) and ``whiteboard.saved`` (whiteboard/api.py). Each card
stores one Discuss Pointer to its record and the neutral System text; the pointer part draws it per viewer at read
time (pointer.EVENTS), so no title, file name or text is copied into the chat.

Where it goes is P3-73's routing (rooms.route): the record's open Team thread, else the Team room. The Client side only
when every client of the room may read the record at the time of the event (resolve.audience_reads: shared, and its
portal section on); the pointer's reader rule checks it again on insert. Nothing is written as a staff-only note.

- A file's revision makes a card only when the file has an open thread or is shared with the client (§3.9: "an
  anchored or shared file"); otherwise every revision in the project would land in the Team room. A file the chat
  made takes no revision (D-453) and never makes a card.
- Canvas saves and file revisions are debounced: one card per record and thread in QUIET_MINUTES, on the first save (a
  leading edge), held by a cache key against two saves at once and by the stored pointers when the cache is gone. An
  Office file is saved in place on every forcesave (office.api, status 6), so its revisions need it as boards do.
- A Locked thread or room (a closed project) gets no card. A handler that fails is logged by core.events and never
  reaches the save that caused it.
"""

import frappe
from frappe.utils import add_to_date, now_datetime

from construction_core.discuss import rooms, send
from construction_core.records.resolve import CLIENT, audience_reads

QUIET_MINUTES = 30  # provisional (no number in the design): see the module note


class DesignEvent:
	"""One app event about one record, as a System card."""

	def __init__(self, doc):
		self.doc = doc

	def holds(self) -> bool:
		"""Whether the event is still true when the job runs."""
		return True

	def author(self) -> str:
		return self.doc.modified_by

	def wanted(self, thread: str) -> bool:
		"""Whether this thread takes a card now (the debounce)."""
		return True

	def post(self) -> str | None:
		"""The System message posted, or None."""
		if not self.holds():
			return None
		thread = rooms.route(self.doc, client=audience_reads(CLIENT, self.doc))
		if frappe.db.get_value("Discuss Thread", thread, "status") == "Locked" or not self.wanted(thread):
			return None
		point = "cc_design_event"
		frappe.db.savepoint(point)
		try:
			return send.post_system(thread, self.author(), targets=[(self.doc.doctype, self.doc.name)])
		except Exception:
			frappe.db.rollback(save_point=point)  # never a card without its pointer: the job commits after a failure
			raise


class DocumentPublished(DesignEvent):
	def holds(self) -> bool:
		return self.doc.status == "Published"


class QuietEvent(DesignEvent):
	"""An event that may come many times a minute: one card per record and thread in QUIET_MINUTES."""

	def wanted(self, thread: str) -> bool:
		key = frappe.cache.make_key(f"cc:design_quiet:{self.doc.doctype}:{self.doc.name}:{thread}")
		if not frappe.cache.set(key, 1, nx=True, ex=QUIET_MINUTES * 60):
			return False
		since = add_to_date(now_datetime(), minutes=-QUIET_MINUTES)
		return not frappe.db.sql("""select 1 from `tabDiscuss Pointer` p
			join `tabDiscuss Message` m on m.name = p.message
			where p.target_type = %s and p.target_name = %s and m.thread = %s and p.creation > %s limit 1""",
			(self.doc.doctype, self.doc.name, thread, since))


class FileRevised(QuietEvent):
	def holds(self) -> bool:
		from construction_core.discuss import media

		f = self.doc
		if f.is_folder or not f.cc_project or f.cc_trashed or f.cc_version_of or media.chat_made(f.name):
			return False
		return bool(f.cc_client_visible) or any(rooms.open_thread("File", f.name, a) for a in ("Internal", "Client"))

	def author(self) -> str:
		return self.doc.cc_rev_by or self.doc.modified_by


class BoardSaved(QuietEvent):
	def author(self) -> str:
		return self.doc.last_saved_by or self.doc.modified_by


EVENTS = {
	"document.published": ("Project Document", DocumentPublished),
	"file.revised": ("File", FileRevised),
	"whiteboard.saved": ("Whiteboard", BoardSaved),
}


def on_event(event: str, doctype: str, doc_name: str):
	"""cc_event_handlers (after the commit, on the short queue)."""
	expected, kind = EVENTS.get(event, (None, None))
	if doctype != expected or not frappe.db.exists(doctype, doc_name):
		return None
	return kind(frappe.get_doc(doctype, doc_name)).post()
