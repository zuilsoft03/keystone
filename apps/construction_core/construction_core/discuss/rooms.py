"""Rooms and threads (D-413, D-418, design §14.1…§14.3): one timeline per audience of a project, and threads in it.

- **A room** is a Discuss Thread whose ``room_key`` is ``<project>|<audience>`` (unique; NULL on every thread, never
  "", the client_id idiom), anchored to its project only. Rooms are got or made by that key with each project and by
  the patch. Its stored title is not used: names are drawn at read time (§14.8). ROOM is the server's flag for the
  room fields; only this module sets it, around the insert of a room.
- **Every other thread** gets ``in_room`` once, before its insert: its project's room for its audience. A supplied
  ``in_room`` that is not that room is refused, so a thread never sits in another project's or audience's room.
- **A thread's root** is the message it was opened on, when that message is in the thread's own room; any other
  thread gets a root card there (a System message whose pointers name the thread, and the message a Team thread is
  about). The Discuss Anchor's ``message_id`` names the root.
- **A thread on a message** is one per (message, audience): it is got or made under a lock on the message row.
- **A client opens a thread** (QR-2) only through ``client_thread``, on a message of the Client room, under OPENER;
  the controller still refuses any other client insert (REST).
- **Follows** (§14.5): Discuss Follow rows are written after the commit by a short job, never in the message's
  transaction: the authors and the people mentioned in a thread, its root message's author, and who opens it; in a
  room only the people mentioned, with the time of the mention (P3-74: Mentions me).
- ``route`` says where a server card about a record goes (D-420).
"""

from functools import partial

import frappe
from frappe import _
from frappe.utils import cint, get_datetime

from construction_core.permissions import client_may_see, is_client, project_of
from construction_core.providers.chat import AUDIENCES

ROOM = "cc_discuss_room"  # holds the key of the room being made; set only in this module
OPENER = "cc_discuss_opener"  # holds the message a client's thread is opened on; set only in client_thread
REASONS = ("mention", "root", "author", "opened")  # a follow keeps the strongest reason it was given


def key(project: str, audience: str) -> str:
	return f"{project}|{audience}"  # P3-32 adds |<company> for partner rooms


def room(project: str, audience: str, own_transaction: bool = False) -> str:
	"""The project's room for ``audience``, made on first use. Two first uses at once meet the unique key, and the
	winner's row is seen only by a fresh snapshot (a savepoint rollback keeps the old one). ``own_transaction``: the
	caller has written nothing else in its transaction (the patch commits before each room), so it is taken back whole
	and the winner read again, as send.py does for a client_id; inside a caller's transaction the loser takes back its
	own insert and asks to try again."""
	found = frappe.db.get_value("Discuss Thread", {"room_key": key(project, audience)})
	if found:
		return found
	point = "cc_room_" + frappe.generate_hash(length=8)
	messages = len(frappe.local.message_log)
	frappe.db.savepoint(point)
	try:
		name = _insert_room(project, audience)
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		del frappe.local.message_log[messages:]  # Frappe's "must be unique" line is not this answer
		if own_transaction:
			frappe.db.rollback()
		else:
			frappe.db.rollback(save_point=point)
		found = frappe.db.get_value("Discuss Thread", {"room_key": key(project, audience)})
		if not found:
			frappe.throw(_("This conversation could not be opened just now. Please try again."))
		return found
	frappe.db.release_savepoint(point)
	return name


def on_project_insert(doc, method=None):
	"""Construction Project after_insert: its Team and Client rooms (partner rooms with P3-32). No other request can
	make them first: the project is not committed yet, and a room's insert reads its project."""
	for audience in AUDIENCES:
		room(doc.name, audience)


def on_project_trash(doc, method=None):
	"""Construction Project on_trash: its rooms go with it while nothing was said in them, so a new project still
	deletes cleanly (DR-7). A room with messages or threads stays, and Frappe's link check refuses the delete, as it
	refused a project with a conversation before rooms. P3-69: the server's design event cards are not something
	said; a room with only those goes with its cards and their pointers. Never raises (DR-7)."""
	try:
		for name in frappe.get_all("Discuss Thread", filters={"project": doc.name, "room_key": ["is", "set"]},
				pluck="name"):
			kinds = frappe.get_all("Discuss Message", filters={"thread": name}, fields=["name", "kind"])
			if any(m.kind != "System" for m in kinds) or frappe.db.exists("Discuss Thread", {"in_room": name}):
				continue
			if kinds:  # by name, never by thread: a message posted since the read above must not go with the room
				cards = [m.name for m in kinds]
				frappe.db.delete("Discuss Pointer", {"message": ["in", cards]})
				frappe.db.delete("Discuss Message", {"name": ["in", cards]})
			frappe.db.delete("Discuss Read State", {"thread": name})
			frappe.db.delete("Discuss Anchor", {"thread_id": name})
			frappe.delete_doc("Discuss Thread", name, ignore_permissions=True, force=True)
	except Exception:
		frappe.log_error(title=f"construction_core: room cleanup failed for {doc.name}")


def place(doc) -> None:
	"""DiscussThread.before_insert: a room keeps its key only under the server's flag, so a forged one comes back as a
	plain thread; any other thread goes into its project's room for its audience."""
	doc.room_key = doc.room_key or None
	if doc.room_key and doc.room_key != frappe.flags.get(ROOM):
		doc.room_key = None
	if doc.room_key:
		doc.in_room = None
		return
	project = project_of(doc)
	if not project or doc.audience not in AUDIENCES:
		return  # validate refuses the thread
	home = room(project, doc.audience)
	if doc.in_room and doc.in_room != home:
		frappe.throw(_("A thread belongs to its project's room for its audience"))
	doc.in_room = home


def check(doc, anchor) -> None:
	"""DiscussThread.validate: what a room or a thread may be anchored to, and the room fields set once. A room is
	anchored to its project; a thread to a record or a message (no other chat row). A staff write that changes a
	room's title or status is refused (P3-59 locks rooms under the flag)."""
	before = doc.get_doc_before_save()
	if before:
		doc.room_key, doc.in_room = before.room_key, before.in_room
		if before.room_key and not frappe.flags.get(ROOM) and (doc.title, doc.status) != (before.title, before.status):
			frappe.throw(_("A room's name and status are set by the system"), frappe.PermissionError)
		return
	if doc.room_key:
		if doc.anchor_doctype != "Construction Project" or doc.room_key != key(doc.anchor_name, doc.audience):
			frappe.throw(_("A room is anchored to its project"))
		return
	if anchor.doctype.startswith("Discuss ") and anchor.doctype != "Discuss Message":
		frappe.throw(_("A thread is opened on a record or a message"))
	if anchor.doctype == "Discuss Message":
		_check_message_anchor(doc, anchor)


def root(doc, anchor_row: str) -> None:
	"""DiscussThread.after_insert, in its transaction: the thread's root message, named on its Discuss Anchor."""
	if doc.room_key:
		return
	if doc.anchor_doctype == "Discuss Message" and \
			frappe.db.get_value("Discuss Message", doc.anchor_name, "thread") == doc.in_room:
		message = doc.anchor_name  # "Reply in thread": the message is the root, no card is added
	else:
		message = card(doc, frappe.session.user)
	frappe.db.set_value("Discuss Anchor", anchor_row, "message_id", message, update_modified=False)


def card(thread, author: str, creation=None, quiet: bool = False) -> str:
	"""A root card for ``thread`` in its room, by the staff member who made it (the thread's owner for migrated cards).
	A Team thread about a client message names that message too."""
	from construction_core.discuss.send import post_system

	targets = [("Discuss Thread", thread.name)]
	if thread.anchor_doctype == "Discuss Message":
		targets.append(("Discuss Message", thread.anchor_name))
	return post_system(thread.in_room, author, targets, creation=creation, quiet=quiet)


def open_thread(anchor_doctype: str, anchor_name: str, audience: str) -> str | None:
	"""The record's open thread for ``audience``, if any. On a message the read is made under a lock on the message
	row, so two first clicks make one thread: the second waits, then meets the first one's thread, or MariaDB 1020 when
	that thread was committed after its snapshot, which its caller answers like any lost race."""
	filters = {"anchor_doctype": anchor_doctype, "anchor_name": anchor_name, "audience": audience,
		"status": ["!=", "Locked"]}
	found = frappe.db.get_value("Discuss Thread", filters, "name")
	if found or anchor_doctype != "Discuss Message":
		return found
	return _locked_open_on(anchor_name, audience)


def client_thread(message: str) -> str:
	"""QR-2: the client's thread on ``message``, a message of the Client room the client reads, opened on first use.
	The rule-3 client checks run on the room (member, portal, section, Client, open). Its first reply goes through the
	normal send and its claim."""
	from construction_core.discuss.checks import client_send

	user = frappe.session.user
	found = frappe.get_list("Discuss Message", filters={"name": message}, fields=["name", "thread"], limit=1,
		user=user) if isinstance(message, str) and message else None
	if not found:
		raise frappe.DoesNotExistError(_("Not found"))
	home = frappe.get_doc("Discuss Thread", found[0].thread)
	client_send(home)
	if not home.room_key:
		frappe.throw(_("A thread is opened on a message of its room"))
	existing = open_thread("Discuss Message", message, "Client")
	if existing:
		return existing
	frappe.flags[OPENER] = message
	try:
		# ignore_permissions: clients have no create (D-387); this flag is the one way, and validate still reads the
		# message as the client and checks the room rules.
		return frappe.get_doc({"doctype": "Discuss Thread", "anchor_doctype": "Discuss Message", "anchor_name": message,
			"audience": "Client", "title": message}).insert(ignore_permissions=True).name
	finally:
		frappe.flags[OPENER] = None


def opener_allowed(doc) -> bool:
	"""DiscussThread.validate: a client's insert is client_thread's own."""
	return doc.anchor_doctype == "Discuss Message" and frappe.flags.get(OPENER) == doc.anchor_name


def follow_message(message) -> None:
	"""DiscussMessage.after_insert: a message in a thread makes its author, the people it mentions and the root
	message's author followers, after the commit. In a room only the people it mentions follow it (P3-74: a room's
	timeline has no other followers, and its unread is the room's own). Each person mentioned by someone else keeps
	the time of the message, for Mentions me. A staff-only note makes or moves no client's follow."""
	in_room = frappe.db.get_value("Discuss Thread", message.thread, "in_room")
	mentions = [u for u in (message.mentions or "").split("\n") if u]
	people = []
	if in_room:
		root = frappe.db.get_value("Discuss Anchor", {"thread_id": message.thread}, "message_id")
		people = [(root and frappe.db.get_value("Discuss Message", root, "author"), "root"), (message.author, "author")]
	follows = {}
	for user, reason in (*people, *((u, "mention") for u in mentions)):
		if user and not (message.staff_only and is_client(user)):
			follows[user] = _stronger(follows.get(user), reason)
	mentioned = sorted(u for u in mentions if u in follows and u != message.author)
	if follows:
		_after_commit(message.thread, follows, mentioned, str(message.creation) if mentioned else None)


def follow_opened(thread, user: str) -> None:
	"""mark_read: who opens a thread follows it (no job when they follow it already)."""
	if thread.in_room and not frappe.db.exists("Discuss Follow", {"thread": thread.name, "user": user}):
		_after_commit(thread.name, {user: "opened"})


def write_follows(thread: str, follows: dict, mentioned=(), mentioned_on: str | None = None) -> None:
	"""The job: one row per (thread, user), keeping the strongest reason and, for ``mentioned``, the newest mention
	time. A lost race (MariaDB 1020, or the unique key) is tried once more on a fresh snapshot; the job wrote nothing
	else."""
	try:
		_write_follows(thread, follows, mentioned, mentioned_on)
	except (frappe.QueryDeadlockError, frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback()
		_write_follows(thread, follows, mentioned, mentioned_on)


def route(doc, client: bool = False) -> str:
	"""Where a server card or event about ``doc`` goes (D-420): the record's open Team thread, else the Team room. The
	Client side only when ``client`` (§3.9 allows the kind for clients) and the client may see the record now. Nothing
	is written as a staff-only note."""
	project = doc.name if doc.doctype == "Construction Project" else project_of(doc)
	audience = "Client" if client and client_may_see(doc) else "Internal"
	if doc.doctype != "Construction Project":
		found = open_thread(doc.doctype, doc.name, audience)
		if found:
			return found
	return room(project, audience)


def _stronger(current: str | None, reason: str) -> str:
	return reason if current is None or REASONS.index(reason) < REASONS.index(current) else current


def _after_commit(thread: str, follows: dict, mentioned=(), mentioned_on: str | None = None) -> None:
	frappe.db.after_commit.add(partial(_queue_follows, thread, follows, list(mentioned), mentioned_on))


def _queue_follows(thread: str, follows: dict, mentioned: list, mentioned_on: str | None) -> None:
	if frappe.in_test:
		# in-process under the test runner, as send._queue_counters does
		write_follows(thread, follows, mentioned, mentioned_on)
		return
	try:
		frappe.enqueue("construction_core.discuss.rooms.write_follows", queue="short", thread=thread, follows=follows,
			mentioned=mentioned, mentioned_on=mentioned_on)
	except Exception:
		frappe.logger("construction_core").exception("The chat follows were not queued")


def _write_follows(thread: str, follows: dict, mentioned=(), mentioned_on: str | None = None) -> None:
	project = frappe.db.get_value("Discuss Thread", thread, "project")
	if not project:
		return
	for user, reason in follows.items():
		at = mentioned_on if user in mentioned else None
		row = frappe.db.get_value("Discuss Follow", {"thread": thread, "user": user}, ["name", "reason", "mentioned_on"],
			as_dict=True)
		if not row:
			# ignore_permissions: the server's row (D-418).
			frappe.get_doc({"doctype": "Discuss Follow", "thread": thread, "project": project, "user": user,
				"reason": reason, "mentioned_on": at}).insert(ignore_permissions=True)
			continue
		changes = {}
		if _stronger(row.reason, reason) != row.reason:
			changes["reason"] = reason
		if at and (not row.mentioned_on or get_datetime(at) > get_datetime(row.mentioned_on)):
			changes["mentioned_on"] = at  # jobs may run out of order: the newest mention wins
		if changes:
			frappe.db.set_value("Discuss Follow", row.name, changes, update_modified=False)


def _insert_room(project: str, audience: str) -> str:
	frappe.flags[ROOM] = key(project, audience)
	try:
		from construction_core.discuss.read import ROOM_WORDS

		# ignore_permissions: a room is the server's row, made for whoever first needs it. Its stored title is the
		# audience's word, for the older screens and Desk; reads draw the names (§14.8).
		return frappe.get_doc({"doctype": "Discuss Thread", "anchor_doctype": "Construction Project",
			"anchor_name": project, "project": project, "audience": audience, "room_key": key(project, audience),
			"title": ROOM_WORDS[audience]}).insert(ignore_permissions=True).name
	finally:
		frappe.flags[ROOM] = None


def _check_message_anchor(doc, message) -> None:
	"""A thread on a message (§14.1): "Reply in thread" on a message of the thread's own room, or a Team thread about a
	client message anywhere in the Client room or its threads ("Discuss with team"). Never on a card or a mirror, which
	belong to their own threads, and one open thread per (message, audience)."""
	if message.kind == "System":
		frappe.throw(_("A thread is opened on a person's message"))
	if cint(message.staff_only):  # an old note (D-419): no thread on it, in any room, on any path
		frappe.throw(_("A thread is opened on a shared message"))
	if cint(message.get("removed")):  # P3-68 audit S2: a removed message starts nothing new, on any path
		frappe.throw(_("This message was removed"), frappe.PermissionError)
	if message.audience == doc.audience:
		if message.thread != doc.in_room:
			frappe.throw(_("A thread is opened on a message of its room"))
	elif not (doc.audience == "Internal" and message.audience == "Client"):
		frappe.throw(_("A thread is opened on a message of its room"))
	if _locked_open_on(message.name, doc.audience):
		frappe.throw(_("This message has a thread already"))


def _locked_open_on(message: str, audience: str) -> str | None:
	frappe.db.sql("select name from `tabDiscuss Message` where name = %s for update", message)
	rows = frappe.db.sql("""select name from `tabDiscuss Thread` where anchor_doctype = 'Discuss Message'
		and anchor_name = %s and audience = %s and status != 'Locked' limit 1 for update""", (message, audience))
	return rows[0][0] if rows else None
