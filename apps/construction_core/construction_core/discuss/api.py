"""Chat API (P1-14, D-098; the extension core, D-358): the team's chats, the portal's conversation and the
Discussion inbox (P3-74, which retired the Desk Client Chat page, D-419).

Rules, enforced here, in the permission layer and in the core modules rather than in the pages:
- Clients read and post only in Client threads, and never see staff-only notes (``permissions.client_may_see``).
- Every write goes through discuss.send; every read through discuss.read and the one exit, discuss.view.respond.
- Typing, pin and seen signals go to the project's staff members' own user rooms only (discuss.live). Whoever types,
  no client is ever told; staff typing therefore never reaches a client, and a client's typing reaches staff.
- Read state is recorded for everyone. Only staff are shown it, and only when the project's ``seen_receipts``
  setting is on (D-098, D-099: per project, off by default).

``thread_view`` and ``post`` keep today's shapes for the four pages that call them (the shell, the portal, the Desk
page and the legacy portal page) until P3-64 moves them to ``messages``, ``message``, ``threads`` and ``send``.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from construction_core.discuss import live, read, rooms
from construction_core.discuss import inbox as room_inbox
from construction_core.discuss import view as chat_view
from construction_core.discuss.checks import MAX_MESSAGE  # noqa: F401  (portal pages read the limit here)
from construction_core.discuss.live import MESSAGE_EVENT, PIN_EVENT, SEEN_EVENT, TYPING_EVENT  # noqa: F401
from construction_core.discuss.live import client_members, staff_members  # noqa: F401  (notifications, boards)
from construction_core.discuss.provider import DiscussChat
from construction_core.discuss.registry import ViewCtx
from construction_core.discuss.send import send_impl
from construction_core.permissions import is_client, switches_once

TYPING_EVERY = 2  # seconds: at most one typing signal per user and thread in this window
LEGACY_THREAD = ("name", "title", "project", "status", "audience")
LEGACY_MESSAGE = ("name", "author", "text", "when", "creation", "mine")
LEGACY_STAFF = ("staff_only", "pinned", "seen_by")


@frappe.whitelist()
def realtime_has_permission(doctype: str, name: str) -> bool:
	"""Replaces ``frappe.realtime.has_permission``, which the realtime server calls for every doc_subscribe and
	doc_open. Clients join no document room: Frappe broadcasts who is viewing a document (doc_viewers) and its
	doc_update to the room, which would show a client the team's presence (P1-14 audit, D-098). Client events go
	to their own user room instead."""
	if is_client(frappe.session.user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	frappe.has_permission(doctype, doc=name, throw=True)
	return True


# --- reads ---------------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def messages(thread: str, cursor: str | None = None, limit: int | str = 50, around: str | None = None,
		after: str | None = None) -> dict:
	"""One page of a thread, newest first, with ``cursor`` (the next older page; None at the start) and ``newer`` (the
	next newer page; None at the newest). ``after``: the page just newer than that message; ``around``: a page with
	that message in its middle (the inbox opens a room at a message, §14.6). A message the caller cannot read answers
	like a missing one (SEC-22)."""
	with switches_once():
		return _messages(thread, cursor, limit, around=around, after=after)


def _messages(thread, cursor, limit, viewer: str | None = None, caller: str | None = None, around=None,
		after=None) -> dict:
	"""``viewer``: whose page it is (None: the session user); ``caller``: the staff preview's own user, whose reads also
	bound every message and card (portal_preview, D-136)."""
	viewer = viewer or frappe.session.user
	t = read.thread_for(viewer, thread)
	ctx = read.context(viewer, t)
	size = read.page_limit(limit)
	if around or after:
		rows, older, newer = _page_at(viewer, t.name, around or after, size, _fields(ctx), whole=bool(around))
	else:
		rows, newer = read.visible_messages(viewer, t.name, cursor, size + 1, _fields(ctx)), None
		more, rows = len(rows) > size, rows[:size]
		older = rows[-1].name if more else None
	out = {"thread": read.thread_out(ctx, t), "messages": chat_view.present(ctx, rows, _reads(ctx, t)),
		"cursor": older, "newer": newer}
	return chat_view.respond(out, viewer, caller=caller, memo=ctx.memo)


def _page_at(viewer: str, thread: str, name, size: int, fields, whole: bool):
	"""(rows newest first, older cursor, newer cursor) for the page newer than ``name`` or, ``whole``, around it: about
	half newer, then ``name`` itself, then older. Three reads; ``name`` is read as the viewer first (SEC-22)."""
	at_row = read.message_at(viewer, thread, name, fields)
	at = (at_row.creation, at_row.name)
	ahead = size // 2 if whole else size
	newer = read.beside(viewer, thread, at, read.NEWER, ahead + 1, fields)
	more_newer, newer = len(newer) > ahead, newer[:ahead]
	rows = list(reversed(newer))
	older = None  # a newer-than page: the caller holds the older messages already
	if whole:
		behind = size - ahead - 1
		before = read.beside(viewer, thread, at, read.OLDER, behind + 1, fields)
		rows += [at_row, *before[:behind]]
		older = rows[-1].name if len(before) > behind else None
	return rows, older, (rows[0].name if more_newer and rows else None)


@frappe.whitelist(methods=["GET"])
def message(name: str) -> dict:
	"""One message, for a live event. A missing message and one the caller may not read answer the same."""
	with switches_once():
		return _message(name)


def _message(name, viewer: str | None = None, caller: str | None = None) -> dict:
	viewer = viewer or frappe.session.user
	found = frappe.get_list("Discuss Message", filters={"name": name}, fields=["thread"], limit=1, user=viewer) \
		if isinstance(name, str) and name else None
	if not found:
		raise frappe.DoesNotExistError(_("Not found"))
	t = read.thread_for(viewer, found[0].thread)
	ctx = read.context(viewer, t)
	rows = frappe.get_list("Discuss Message", filters={"name": name}, fields=list(_fields(ctx)), user=viewer)
	out = chat_view.respond({"messages": chat_view.present(ctx, rows, _reads(ctx, t))}, viewer, caller=caller,
		memo=ctx.memo)
	if not out["messages"]:  # the preview's caller may not read it: the same answer as a missing one
		raise frappe.DoesNotExistError(_("Not found"))
	return out["messages"][0]


@frappe.whitelist(methods=["GET"])
def threads(project: str) -> list:
	"""The project's threads the caller reads, with their unread counts (one grouped query); a thread in a room also
	carries its root, replies, whether the caller follows it and its newest reply's author and time (P3-64)."""
	return _threads(project)


def _threads(project, viewer: str | None = None, caller: str | None = None) -> list:
	"""``caller``: the staff preview's user; a thread the caller does not read is left out, never named."""
	viewer = viewer or frappe.session.user
	if not (isinstance(project, str) and project
			and frappe.has_permission("Construction Project", "read", doc=project, user=viewer, throw=False)):
		raise frappe.DoesNotExistError(_("Not found"))
	staff = not is_client(viewer)
	# The project was just read as the viewer: its threads' titles ask it no more (rooms name no record).
	memo, counts = {("Construction Project", project, viewer): True}, read.unread(viewer, project)
	rows = read.thread_rows(viewer, project)
	if caller:
		rows = _caller_reads_threads(rows, caller)
	extras = read.thread_extras(viewer, project, rows)  # P3-64: root, following and the newest reply, for reply lines
	out = []
	for t in rows:
		row = read.thread_out(ViewCtx(user=viewer, thread=t, staff=staff, memo=memo), t)
		row["unread"] = counts.get(t.name, 0)
		if t.name in extras:
			extra = extras[t.name]
			row.update(extra, last_by=chat_view.person(extra["last_by"]) if extra["last_by"] else None)
		out.append(row)
	return chat_view.strip(out)


@frappe.whitelist(methods=["GET"])
def discussion_inbox(project: str | None = None, closed: int | str = 0, show: str | None = None,
		start: int | str = 0) -> dict:
	"""The caller's rooms across their projects (§14.6, D-414), a page of 50: unread, the newest line and, for staff,
	Needs a reply and mentions, with the filters ``show`` (unread, reply, mentions), ``project`` and ``closed``."""
	with switches_once():
		return room_inbox.discussion_inbox(frappe.session.user, project, closed, show, start)


@frappe.whitelist(methods=["GET"])
def resolve(thread: str) -> dict:
	"""Where an old link to a conversation now leads (§14.7): its room, and the root message the thread hangs off (None
	for a room). A missing thread and one the caller may not read answer the same "not found" (§14.4 row 1)."""
	t = read.thread_for(frappe.session.user, thread)
	root = frappe.db.get_value("Discuss Anchor", {"thread_id": t.name}, "message_id") if t.in_room else None
	return {"thread": t.name, "room": t.in_room or t.name, "root": root}


@frappe.whitelist()
def thread_view(thread: str) -> dict:
	"""Today's shape (an adapter until P3-64): the thread's newest 50 messages, oldest first. Clients get no staff
	notes, pins or read state."""
	t = _thread(thread)
	viewer = frappe.session.user
	memo = {}
	if is_client(viewer):
		return legacy_view(chat_view.respond(client_thread_view(t, memo=memo), viewer, memo=memo))
	ctx = ViewCtx(user=viewer, thread=t, staff=True, memo=memo)
	show_seen = seen_receipts_on(t.project)
	reads = frappe.get_all("Discuss Read State", filters={"thread": thread}, fields=["user", "last_read_on"]) \
		if show_seen else None
	rows = list(reversed(read.visible_messages(viewer, thread, fields=read.STAFF_FIELDS)))
	out = {"thread": _thread_row(ctx, t), "messages": chat_view.present(ctx, rows, reads),
		"pinned": chat_view.present(ctx, read.pinned(viewer, thread), reads)}  # pins of any page, not only the newest
	out = legacy_view(chat_view.respond(out, viewer, memo=memo))
	out["seen_receipts"] = show_seen
	return out


def client_thread_view(t, user: str | None = None, memo: dict | None = None) -> dict:
	"""One thread as a client reads it: no staff notes, pins or read state. ``user`` is that client (None: the
	session user). Not whitelisted: thread_view serves clients, and the staff preview (P3-05) passes its client. Its
	cards keep ``_ref``, which respond() checks and strips; both callers pass it through respond()."""
	if not frappe.has_permission("Discuss Thread", "read", doc=t, user=user):
		raise frappe.PermissionError
	viewer = user or frappe.session.user
	ctx = ViewCtx(user=viewer, thread=t, staff=False, memo={} if memo is None else memo)
	rows = list(reversed(read.visible_messages(viewer, t.name)))
	return {"thread": _thread_row(ctx, t), "messages": chat_view.present(ctx, rows)}


def legacy_view(view: dict) -> dict:
	"""A responded view in thread_view's keys: a message's first attachment card as ``attachment``."""
	for key in chat_view.MESSAGE_LISTS:
		if key in view:
			view[key] = [legacy_message(m) for m in view[key]]
	return view


def legacy_message(m: dict) -> dict:
	out = {k: m[k] for k in LEGACY_MESSAGE}
	out["attachment"] = ((m.get("parts") or {}).get("attachments") or [None])[0]
	out.update({k: m[k] for k in LEGACY_STAFF if k in m})
	return out


# --- writes --------------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def send(thread: str, text: str, client_id: str | None = None, staff_only: int | str = 0, parts=None,
		also_room: int | str = 0) -> str:
	"""Make a message (D-392). ``client_id`` makes a retry safe; ``parts`` is a JSON object of registered parts;
	``also_room`` also shows a thread reply in its room (§14.2, staff and clients alike, QR-2)."""
	return send_impl(thread, text, client_id=client_id, staff_only=staff_only, parts_in=parts, also_room=also_room)


@frappe.whitelist(methods=["POST"])
def discuss_with_team(message: str) -> dict:
	"""The one Team-room thread about a client's message (§14.1), made on first use; a second click opens the same
	thread. It opens in the Team room. Nothing the client reads changes: the root card is in the Team room."""
	_staff_only()
	found = frappe.get_list("Discuss Message", filters={"name": message}, fields=["name", "project", "audience",
		"author"], limit=1) if isinstance(message, str) and message else None
	if not found:
		raise frappe.DoesNotExistError(_("Not found"))
	m = found[0]
	if m.audience != "Client" or not is_client(m.author):
		frappe.throw(_("Discuss with team is for a client's message"))
	thread = lost_race_once(lambda: DiscussChat().ensure_thread("Discuss Message", m.name, "Internal"))
	return {"thread": thread, "room": rooms.room(m.project, "Internal")}


def lost_race_once(open_):
	"""An endpoint's open that lost a race (MariaDB 1020 under a lock, rooms.open_thread) is tried once more on a
	fresh snapshot: the endpoint wrote nothing before it, so it is taken back whole."""
	try:
		return open_()
	except frappe.QueryDeadlockError:
		frappe.db.rollback()
		return open_()


@frappe.whitelist(methods=["POST"])
def post(thread: str, content: str, staff_only: int | str = 0) -> str:
	# No mark_read here (F15, D-353): the page marks the thread read after a send, and a read-state write that loses a
	# race (MariaDB 1020) inside this transaction rolled the whole message back and answered 500.
	return send_impl(thread, content, staff_only=staff_only)


@frappe.whitelist(methods=["POST"])
def mark_read(thread: str):
	t = _thread(thread)
	user = frappe.session.user
	if not _record_read(t, user):
		# Lost a race with another request of this reader (F15, D-353). This request has written nothing else, so the
		# whole transaction is taken back and the write is tried once more on a fresh snapshot; if that loses too, the
		# other request has marked the thread read, and this one only gives way (no notice clearing, no signal).
		frappe.db.rollback()
		if not _record_read(t, user):
			frappe.db.rollback()
			return
	from construction_core.notifications import clear_thread

	rooms.follow_opened(t, user)  # who opens a thread follows it, after the commit (§14.5)
	clear_thread(user, thread)  # P3-06: opening a conversation clears the reader's own notices about it
	live.read_event(user, t.name)  # P3-74: the reader's other tabs drop the count, after the commit
	if seen_receipts_on(t.project):
		live.staff_event(t.project, SEEN_EVENT, {"thread": thread, "user": user}, exclude=user)


@frappe.whitelist(methods=["POST"])
def typing(thread: str):
	"""Tell the project's staff that the caller is typing. Never published to a client (D-098)."""
	t = _thread(thread)
	user = frappe.session.user
	if not frappe.cache.set(f"cc:typing:{thread}:{user}", 1, nx=True, ex=TYPING_EVERY):
		return
	live.staff_event(t.project, TYPING_EVENT, {"thread": thread, **chat_view.person(user)}, exclude=user)


@frappe.whitelist(methods=["POST"])
def set_pinned(message: str, pinned: int | str = 1):
	"""Pin or unpin a message for the team. Pins are staff information; clients never see them."""
	_staff_only()
	m = frappe.get_doc("Discuss Message", message)
	m.check_permission("read")
	if m.removed:  # P3-68: a removed message lost its pin and takes no new one
		frappe.throw(_("This message cannot be changed"), frappe.PermissionError)
	pinned = cint(pinned)
	user = frappe.session.user
	# db_set: messages are append-only (DiscussMessage.validate); the pin is team metadata, not the message.
	m.db_set({"pinned": pinned, "pinned_by": user if pinned else None, "pinned_on": now_datetime() if pinned else None},
		update_modified=False)
	live.staff_event(m.project, PIN_EVENT, {"thread": m.thread, "message": m.name, "pinned": pinned})


# --- helpers -------------------------------------------------------------------------------------------------------


def _caller_reads_threads(rows, caller: str) -> list:
	names = [t.name for t in rows]
	read_by_caller = set(frappe.get_list("Discuss Thread", filters={"name": ["in", names or [""]]}, pluck="name",
		limit=len(names) or 1, user=caller))
	return [t for t in rows if t.name in read_by_caller]


def seen_receipts_on(project: str) -> bool:
	return bool(cint(frappe.db.get_value("Workspace Config", project, "seen_receipts")))


def _thread(thread: str):
	doc = frappe.get_doc("Discuss Thread", thread)
	doc.check_permission("read")
	return doc


def _staff_only():
	if is_client(frappe.session.user):
		frappe.throw(_("This is for the project team only"), frappe.PermissionError)


def _thread_row(ctx: ViewCtx, t) -> dict:
	row = {k: t.get(k) for k in LEGACY_THREAD}
	row["title"] = read.title_for(ctx, t)
	return row


def _fields(ctx: ViewCtx) -> tuple:
	return read.STAFF_FIELDS if ctx.staff else read.FIELDS


def _reads(ctx: ViewCtx, t) -> list | None:
	if not (ctx.staff and seen_receipts_on(t.project)):
		return None
	return frappe.get_all("Discuss Read State", filters={"thread": t.name}, fields=["user", "last_read_on"])


def _record_read(t, user: str) -> bool:
	"""Write the reader's read state; False when the write lost a race with another request of the same reader (MariaDB
	1020, a deadlock, or the unique (thread, user) key, F7). Never retried in the same transaction: the caller rolls
	back and tries again, and the second try finds the winner's row and updates it."""
	point = "cc_read_" + frappe.generate_hash(length=8)
	messages = len(frappe.local.message_log)
	frappe.db.savepoint(point)
	try:
		mine = {"thread": t.name, "user": user}
		if frappe.db.get_value("Discuss Read State", mine):
			frappe.db.set_value("Discuss Read State", mine, "last_read_on", now_datetime(), update_modified=False)
		else:
			# ignore_permissions: a user records only their own read state, on a thread they may read (checked by the caller).
			frappe.get_doc({"doctype": "Discuss Read State", "thread": t.name, "project": t.project, "user": user,
				"last_read_on": now_datetime()}).insert(ignore_permissions=True)
	except (frappe.QueryDeadlockError, frappe.DuplicateEntryError, frappe.UniqueValidationError):
		del frappe.local.message_log[messages:]  # Frappe's "must be unique" line is not this answer
		# A true deadlock (1213) rolls the whole transaction back and takes the savepoint with it, so this is best effort.
		try:
			frappe.db.rollback(save_point=point)
		except Exception:
			pass
		return False
	frappe.db.release_savepoint(point)
	return True
