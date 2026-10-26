"""Chat reads (design §13.1 S3, rule 9): every message read, count and cursor goes through visible_messages, which is
Frappe's get_list as the viewer, so the §2.1 predicate and the client rules decide (staff-only notes, Internal
threads, the portal and section switches). Nothing here reads messages with get_all or db.count.

- Pages are newest first, PAGE at a time. A cursor is opaque: the name of the last message of the viewer's previous
  page. One the viewer cannot read in this thread answers like a missing one (SEC-22). P3-74 adds the newer-than
  cursor and a page around one message (the inbox opens a room at a message, §14.6), under the same rule.
- ``threads`` gives each thread's unread count in one grouped query over the viewer's own visible messages.
- A viewer who cannot read a thread's record sees "Conversation" as its title (F11, D-370). A room's stored title is
  not used: staff see "Team" or "Client", a client the firm's name (§14.8), until P3-64 draws the words.
- Thread reads carry ``in_room``; rooms are listed first (the legacy adapters, §14.7).
- ``thread_extras`` (P3-64) reads each thread's root, reply count and newest reply from the viewer's own visible set
  (get_list as the viewer, run=False, as ``unread`` does), leaving out notes and System cards (§14.5).
"""

import frappe
from frappe import _
from frappe.query_builder.terms import NamedParameterWrapper
from frappe.utils import cint

from construction_core.discuss import parts
from construction_core.discuss.provider import PAGE
from construction_core.discuss.registry import ViewCtx, sender_of
from construction_core.onboarding.mail import brand
from construction_core.permissions import is_client

FIELDS = ("name", "author", "content", "creation", "file", "kind", "staff_only", "mentions", "edited", "removed",
	"reactions", "agreed")  # permlevel 0: every viewer (mentions: P3-66, the chips are drawn from the row, with no query;
# P3-68: edited, removed, Agreed and the reaction summary, kept on the row so a page reads nothing more for them)
STAFF_FIELDS = (*FIELDS, "pinned")  # permlevel 1: the team's pins
THREAD_FIELDS = ("name", "title", "project", "audience", "status", "anchor_doctype", "anchor_name", "last_message_on",
	"room_key", "in_room", "message_count")
NEUTRAL = "Conversation"
ROOM_WORDS = {"Internal": "Team", "Client": "Client"}  # what staff call a room until P3-64's words
ORDER = "creation desc, name desc"  # name breaks ties: rows may share a creation
ORDER_ASC = "creation asc, name asc"
OLDER, NEWER = "older", "newer"


def visible_messages(viewer: str, thread: str, cursor: str | None = None, limit: int = PAGE,
		fields=FIELDS, only: dict | None = None) -> list:
	"""The thread's messages ``viewer`` may read, newest first, older than ``cursor``. ``only``: more filters that narrow
	the visible set, never widen it (the gallery's kind, P3-65)."""
	at = (_cursor_creation(viewer, thread, cursor), cursor) if cursor else None
	return beside(viewer, thread, at, OLDER, limit, fields, only)


def beside(viewer: str, thread: str, at, side: str, limit: int = PAGE, fields=FIELDS, only: dict | None = None) -> list:
	"""The thread's messages ``viewer`` may read on one ``side`` of ``at`` (creation, name), nearest first: OLDER is
	newest first, NEWER oldest first (P3-74's newer-than cursor). ``at`` None: the newest messages."""
	filters, or_filters = {**(only or {}), "thread": thread}, None
	if at:
		creation, name = at
		op = "<" if side == OLDER else ">"
		# (creation, name) < (c, n), as (creation <= c) and (creation < c or name < n); the same with > for NEWER
		filters["creation"] = [op + "=", creation]
		or_filters = {"creation": [op, creation], "name": [op, name]}
	return frappe.get_list("Discuss Message", filters=filters, or_filters=or_filters, fields=list(fields),
		order_by=ORDER if side == OLDER else ORDER_ASC, limit=limit, user=viewer)


def message_at(viewer: str, thread: str, name, fields=FIELDS) -> frappe._dict:
	"""One message of the thread as ``viewer`` reads it; one they cannot read answers like a missing one (SEC-22)."""
	row = frappe.get_list("Discuss Message", filters={"thread": thread, "name": name}, fields=list(fields), limit=1,
		user=viewer) if isinstance(name, str) and name else None
	if not row:
		raise frappe.DoesNotExistError(_("Not found"))
	return row[0]


def pinned(viewer: str, thread: str) -> list:
	"""The thread's newest PAGE pinned messages, oldest first: staff information (D-098)."""
	rows = frappe.get_list("Discuss Message", filters={"thread": thread, "pinned": 1}, fields=list(STAFF_FIELDS),
		order_by=ORDER, limit=PAGE, user=viewer)
	return list(reversed(rows))


def context(viewer: str, thread) -> ViewCtx:
	return ViewCtx(user=viewer, thread=thread, staff=sender_of(viewer) == "staff")


def thread_for(viewer: str, name) -> frappe._dict:
	"""The thread row, or the same refusal for a missing thread and one the viewer may not read."""
	row = frappe.db.get_value("Discuss Thread", name, list(THREAD_FIELDS), as_dict=True) \
		if isinstance(name, str) and name else None
	if not row or not frappe.has_permission("Discuss Thread", "read", doc=name, user=viewer, throw=False):
		raise frappe.DoesNotExistError(_("Not found"))
	return row


def title_for(ctx: ViewCtx, t) -> str:
	if t.get("room_key"):
		return ROOM_WORDS.get(t.audience, NEUTRAL) if ctx.staff else (brand() or NEUTRAL)
	if t.anchor_doctype and t.anchor_name and ctx.can_read(t.anchor_doctype, t.anchor_name):
		return t.title
	return NEUTRAL


def capabilities(ctx: ViewCtx, t) -> list[str]:
	return [p.key for p in parts.PARTS if p.capable and t.audience in p.audiences and p.capable(ctx, t)]


def thread_out(ctx: ViewCtx, t) -> dict:
	"""P3-64 adds, for a thread in a room: ``replies`` (its counter: no notes, no cards) and ``about``, the message it
	was opened on ("Reply in thread", or the client message of a "Discuss with team" thread), which the reader of the
	thread reads too."""
	in_room = t.get("in_room")
	return {"name": t.name, "title": title_for(ctx, t), "status": t.status, "audience": t.audience,
		"in_room": in_room, "last_message_on": t.last_message_on, "capabilities": capabilities(ctx, t),
		"replies": cint(t.get("message_count")) if in_room else None,
		"about": t.anchor_name if in_room and t.anchor_doctype == "Discuss Message" else None}


def thread_extras(viewer: str, project: str, threads) -> dict:
	"""P3-64: {thread: {root, topic, topic_kind, following, last_by, last_on, replies}} for the threads in rooms, in one query for
	any number (and for none): the root message on its Discuss Anchor (where its reply line is drawn) with its replies
	and newest reply by §14.5's last-message rule (not a note, not a card), and whether the viewer follows each
	(Discuss Follow, unique per thread and user, §14.5), and whether that follow holds a mention newer than the viewer's
	read state (P3-66's Mentions filter, the inbox's Mentions me rule). The messages are the viewer's own visible set, built by get_list as unread() builds it
	(run=False), so the predicate is Frappe's (F5); the counter, written by a job after the commit, may lag."""
	names = [t.name for t in threads if t.get("in_room")] or [""]
	params = NamedParameterWrapper()
	visible = frappe.get_list("Discuss Message", filters={"project": project, "staff_only": 0, "kind": ["!=", "System"],
		"removed": 0}, fields=["name", "thread", "author", "creation", "content", "kind"], user=viewer, run=False).get_sql(
		param_wrapper=params)
	rows = frappe.db.sql(f"""select a.thread_id as thread, a.message_id as root, m.author, m.creation, x.replies,
			r.content as topic, r.kind as topic_kind, f.name as follow,
			f.mentioned_on is not null and (rs.last_read_on is null or f.mentioned_on > rs.last_read_on) as mentioned
		from `tabDiscuss Anchor` a
		left join `tabDiscuss Follow` f on f.thread = a.thread_id and f.user = %(cc_viewer)s
		left join `tabDiscuss Read State` rs on rs.thread = a.thread_id and rs.user = %(cc_viewer)s
		left join ({visible}) r on r.name = a.message_id
		left join (select v.thread, max(v.creation) as newest, count(*) as replies from ({visible}) v
			where v.thread in %(cc_names)s group by v.thread) x on x.thread = a.thread_id
		left join ({visible}) m on m.thread = x.thread and m.creation = x.newest
		where a.thread_id in %(cc_names)s""", {**params.parameters, "cc_names": tuple(names), "cc_viewer": viewer},
		as_dict=True)
	return {r.thread: {"root": r.root, "following": bool(r.follow), "last_by": r.author,
		"last_on": str(r.creation) if r.creation else None, "replies": cint(r.replies), "topic": _topic(r.topic),
		"topic_kind": r.topic_kind or None,  # P3-65: a photo's thread has no text; the screen names it by its kind
		"mentioned": bool(cint(r.mentioned))}  # P3-66: the Mentions filter, an unread mention of the viewer (§14.6)
		for r in rows}


def _topic(content) -> str | None:
	"""A thread off a message is named by its root's first line (a client's thread is stored under the message's name)."""
	from construction_core.discuss.view import plain

	line = next((ln.strip() for ln in plain(content).splitlines() if ln.strip()), "") if content else ""
	return line[:80] or None


def rooms_first(rows: list) -> list:
	"""Rooms before threads, the Team room before the Client room; the rest keep their order."""
	return sorted(rows, key=lambda t: (0, t.audience != "Internal") if t.get("room_key") else (1, False))


def page_limit(limit) -> int:
	return min(max(cint(limit) or PAGE, 1), PAGE)


def thread_rows(viewer: str, project: str) -> list:
	return rooms_first(frappe.get_list("Discuss Thread", filters={"project": project}, fields=list(THREAD_FIELDS),
		order_by="last_message_on desc, creation desc", limit=500, user=viewer))


def counted_sql(viewer: str, filters: dict, fields: list, params) -> str:
	"""The SQL of the viewer's visible messages that count as unread (§14.5), for the three counts below: get_list builds
	the visible set (run=False), so the predicate is Frappe's own. System cards and mirrors are not counted, but for a
	client who is a confirmed approver (P3-78, N11, §3.12) the Open approval cards of their projects' requests are: an
	exception to the hub's System-card rule, from the same one read (a pointer to an Open request their project's
	approvals section shows). A contact still waiting for the second staff confirmation is no approver here: the join on
	their latest designation event is ``approvals.api.approvers``' rule (test_approvals_portal holds the two equal)."""
	if not is_client(viewer):
		return frappe.get_list("Discuss Message", filters={**filters, "kind": ["!=", "System"]}, fields=fields, user=viewer,
			run=False).get_sql(param_wrapper=params)
	visible = frappe.get_list("Discuss Message", filters=filters, fields=[*fields, "kind"], user=viewer,
		run=False).get_sql(param_wrapper=params)
	params.parameters["cc_approver"] = viewer
	return f"""select {", ".join(f"v.`{f}`" for f in fields)} from ({visible}) v where ifnull(v.kind, '') != 'System'
		or v.name in (select p.message
			from `tabDiscuss Pointer` p join `tabApproval Request` r on r.name = p.target_name and r.status = 'Open'
				and r.decider_party = 'client'
			join `tabProject Member` pm on pm.parenttype = 'Construction Project' and pm.parent = r.project
				and pm.user = %(cc_approver)s and pm.may_approve = 1
			join `tabApproval Event` d on d.project = r.project and d.kind = 'designation'
				and json_value(d.canonical, '$.body.user') = %(cc_approver)s
				and json_value(d.canonical, '$.body.may_approve') = '1' and json_value(d.canonical, '$.body.state') = 'Confirmed'
				and d.seq = (select max(d2.seq) from `tabApproval Event` d2 where d2.project = r.project
					and d2.kind = 'designation' and json_value(d2.canonical, '$.body.user') = %(cc_approver)s)
			join `tabWorkspace Section` s on s.parenttype = 'Workspace Config' and s.parent = r.project
				and s.section = 'approvals' and s.client_visible = 1
			where p.target_type = 'Approval Request')"""


def unread(viewer: str, project: str) -> dict:
	"""{thread: messages by others after the viewer's read state}, from the viewer's own visible messages: one query.
	Which messages count is counted_sql's."""
	params = NamedParameterWrapper()  # Frappe's own parameters, as query.run() would pass them
	sql = counted_sql(viewer, {"project": project, "author": ["!=", viewer], "removed": 0}, ["name", "thread", "creation"],
		params)
	return dict(frappe.db.sql(f"""select m.thread, count(*) from ({sql}) m
		left join `tabDiscuss Read State` r on r.thread = m.thread and r.user = %(viewer)s
		where r.last_read_on is null or m.creation > r.last_read_on
		group by m.thread""", {**params.parameters, "viewer": viewer}))


def _cursor_creation(viewer: str, thread: str, cursor):
	row = frappe.get_list("Discuss Message", filters={"thread": thread, "name": cursor}, fields=["creation"],
		limit=1, user=viewer) if isinstance(cursor, str) else None
	if not row:
		raise frappe.DoesNotExistError(_("Not found"))
	return row[0].creation
