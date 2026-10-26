"""The Discussion inbox (design §14.5, §14.6; D-414): the reader's rooms across their projects, in the same number of
queries for one project or thirty.

Reads, in order: the projects, their rooms, the reader's follows, the unread grouped per room and joined to read state,
and the newest line per room; then present() and respond() (the rows sit in ``rooms``, which respond walks).
- Staff: their member projects (``allowed_projects``), the active ones unless ``closed`` (Completed or Cancelled; On
  hold counts as active until P3-59 says what closing is). Filters: unread, reply (Needs a reply), mentions. ``project``
  narrows to one member project at any status (the room list inside a project). Totals count rooms, over the whole
  selection, before the filter.
- Clients: the Client rooms get_list lets them read, so a project with the portal or its Discussion section off drops
  out (D-117). No Needs a reply, no mentions, no filters (§14.4's inbox row); respond() refuses the staff keys.
- Unread (§14.5): ``unread`` counts room messages by others after the reader's read state of the room; ``in_threads``
  counts replies by others in the threads the reader follows, after their read state of each thread. System cards and
  mirrors never count (a confirmed approver's Open approval cards do, P3-78, N11: read.counted_sql). Both come from the reader's own visible messages (get_list as the reader, run=False).
- The line: the newest message in the room or its threads that is not System and not a note (staff_only 0), so one
  summary serves every reader of the room. For staff it also decides Needs a reply: a client wrote it, by account kind
  ("team" means not a client until P3-27, D-409). Removed messages join with P3-68.
- Mentions (staff): an unread mention, a Discuss Follow ``mentioned_on`` in the room or one of its threads newer than
  the reader's read state of that conversation; reading it clears the mark.
- Clients cost the same for one project or many: switches_once reads a client's switches for all their projects.
- ``around`` and ``open_thread`` say where a click opens: the room at that message, or at the thread's root with the
  thread open (§14.6).
"""

import frappe
from frappe import _
from frappe.query_builder.terms import NamedParameterWrapper
from frappe.utils import cint, date_diff, get_datetime, nowdate

from construction_core.discuss import read
from construction_core.discuss import view as chat_view
from construction_core.discuss.registry import ViewCtx
from construction_core.permissions import allowed_projects, is_client

PAGE = 50  # rooms
CLOSED = ("Completed", "Cancelled")
SHOWS = ("", "unread", "reply", "mentions", "waiting")
AUDIENCE_ORDER = ("Client", "Internal")  # within a project, as the canvas lists them; partner rooms follow (P3-32)


def discussion_inbox(viewer: str, project=None, closed=0, show=None, start=0) -> dict:
	return Inbox(viewer, project, closed, show, start).run()


class Inbox:
	def __init__(self, viewer: str, project=None, closed=0, show=None, start=0):
		self.viewer = viewer
		self.staff = not is_client(viewer)
		self.project = project if isinstance(project, str) and project else None
		self.closed = self.staff and bool(cint(closed))
		self.show = (show or "") if self.staff else ""
		if self.show not in SHOWS:
			frappe.throw(_("Unknown filter"), frappe.ValidationError)
		self.start = max(cint(start), 0)
		self.fields = read.STAFF_FIELDS if self.staff else read.FIELDS
		self.memo = {}

	def run(self) -> dict:
		projects = self.projects()
		rooms = self.rooms(list(projects))
		names = [t.name for t in rooms]
		followed, mentioned = self.follows(names)
		counts = self.counts(names + followed)
		newest = self.newest(list(projects), names)
		self.on_clients = self.waiting(list(projects)) if self.staff and rooms else {}
		rows = self.ordered([self.row(t, counts.get(t.name), newest.get(t.name), mentioned) for t in rooms],
			rooms, newest)
		chosen = [r for r in rows if self.keeps(r)]
		page = chosen[self.start:self.start + PAGE]
		self.draw(page, newest)
		order = list(dict.fromkeys(r["project"] for r in rows))
		out = {"projects": [_project_out(projects[p]) for p in order], "rooms": page, "totals": self.totals(rows),
			"more": len(chosen) > self.start + PAGE}
		return chat_view.respond(out, self.viewer, memo=self.memo)

	# --- the reads: one query each, whatever the number of projects or rooms ---------------------------------------

	def projects(self) -> dict:
		member = [p for p in allowed_projects(self.viewer) if not self.project or p == self.project]
		if not member:
			return {}
		filters = {"name": ["in", member]}
		if self.staff and not self.project:
			filters["status"] = ["in", list(CLOSED)] if self.closed else ["not in", list(CLOSED)]
		rows = frappe.get_list("Construction Project", filters=filters, fields=["name", "project_name", "status"],
			limit=len(member), user=self.viewer)
		return {r.name: r for r in rows}

	def rooms(self, projects: list) -> list:
		if not projects:
			return []
		return frappe.get_list("Discuss Thread", filters={"project": ["in", projects], "room_key": ["is", "set"]},
			fields=["name", "project", "audience", "room_key", "creation"], order_by="creation asc, name asc",
			user=self.viewer)

	def follows(self, rooms: list) -> tuple[list, set]:
		"""The threads of these rooms the reader follows, and (staff) the rooms with an unread mention of the reader: a
		mention in the room or one of its threads newer than the reader's read state of that conversation."""
		if not rooms:
			return [], set()
		rows = frappe.db.sql("""select f.thread, t.in_room, coalesce(t.in_room, t.name) as room,
				f.mentioned_on is not null and (r.last_read_on is null or f.mentioned_on > r.last_read_on) as mention
			from `tabDiscuss Follow` f
			join `tabDiscuss Thread` t on t.name = f.thread
			left join `tabDiscuss Read State` r on r.thread = f.thread and r.user = f.user
			where f.user = %(user)s and (t.in_room in %(rooms)s or t.name in %(rooms)s)""",
			{"user": self.viewer, "rooms": tuple(rooms)}, as_dict=True)
		mentioned = {r.room for r in rows if cint(r.mention)} if self.staff else set()
		return [r.thread for r in rows if r.in_room], mentioned

	def counts(self, threads: list) -> dict:
		"""{room: (new, in_threads)} from the reader's visible messages by others, after their read state."""
		if not threads:
			return {}
		params = NamedParameterWrapper()
		visible = read.counted_sql(self.viewer, {"thread": ["in", threads], "author": ["!=", self.viewer]},
			["name", "thread", "creation"], params)
		rows = frappe.db.sql(f"""select coalesce(t.in_room, m.thread) as room, sum(t.in_room is null) as new,
				sum(t.in_room is not null) as in_threads
			from ({visible}) m join `tabDiscuss Thread` t on t.name = m.thread
			left join `tabDiscuss Read State` r on r.thread = m.thread and r.user = %(cc_viewer)s
			where r.last_read_on is null or m.creation > r.last_read_on
			group by coalesce(t.in_room, m.thread)""", {**params.parameters, "cc_viewer": self.viewer}, as_dict=True)
		return {r.room: (cint(r.new), cint(r.in_threads)) for r in rows}

	def newest(self, projects: list, rooms: list) -> dict:
		"""{room: row}: the newest message of the room and its threads, not System and not a note, ties broken by name,
		with its author's User row and the root of its thread (for opening at it).

		Index-driven: each conversation of the rooms (the room and the threads in it, found through the project index)
		names its newest such message by a backward walk of (thread, creation, name), usually one row. That name is the
		summary every reader of the room shares (§14.5); the row itself comes only from the reader's own visible set
		(get_list as the reader), so a summary the reader cannot read gives no line (fail closed)."""
		if not rooms:
			return {}
		params = NamedParameterWrapper()
		visible = frappe.get_list("Discuss Message", filters={"project": ["in", projects], "staff_only": 0,
			"kind": ["!=", "System"]}, fields=[*self.fields, "thread"], user=self.viewer,
			run=False).get_sql(param_wrapper=params)
		rows = frappe.db.sql(f"""select z.* from (select v.*, coalesce(c.in_room, c.name) as cc_room,
				a.message_id as cc_root, u.full_name as cc_full_name, u.user_image as cc_image, u.user_type as cc_type,
				row_number() over (partition by coalesce(c.in_room, c.name) order by v.creation desc, v.name desc)
					as cc_rank
			from `tabDiscuss Thread` c
			join ({visible}) v on v.name = (select m.name from `tabDiscuss Message` m
				where m.thread = c.name and m.staff_only = 0 and ifnull(m.kind, '') != 'System'
				order by m.creation desc, m.name desc limit 1)
			left join `tabDiscuss Anchor` a on c.in_room is not null and a.thread_id = c.name
			left join `tabUser` u on u.name = v.author
			where c.project in %(cc_projects)s and (c.name in %(cc_rooms)s or c.in_room in %(cc_rooms)s)) z
			where z.cc_rank = 1""", {**params.parameters, "cc_rooms": tuple(rooms), "cc_projects": tuple(projects)},
			as_dict=True)
		return {r.cc_room: r for r in rows}

	def waiting(self, projects: list) -> dict:
		"""{project: its "Waiting on clients" line} (approvals design §3.12, P3-80): the Open requests the reader reads
		(the request's own rule, get_list as the reader), with each project's confirmed approvers, in one grouped read.
		The line names the oldest: "Waiting on Rachel Lim: VO-0007, 3 days"."""
		from construction_core.approvals.api import CONFIRMED  # here: approvals imports discuss

		params = NamedParameterWrapper()
		visible = frappe.get_list("Approval Request", filters={"project": ["in", projects], "status": "Open"},
			fields=["name", "project", "subject_name", "creation"], user=self.viewer,
			run=False).get_sql(param_wrapper=params)
		# the member columns, not the chain: approvals.api.guard lets only the chain's own writes change them
		rows = frappe.db.sql(f"""select v.name, v.project, v.subject_name, v.creation,
				group_concat(distinct u.full_name order by u.full_name separator ', ') as people
			from ({visible}) v
			left join `tabProject Member` pm on pm.parenttype = 'Construction Project' and pm.parent = v.project
				and pm.may_approve = 1 and pm.approver_state = %(cc_confirmed)s
			left join `tabUser` u on u.name = pm.user and u.enabled = 1 and u.user_type = 'Website User'
			group by v.name, v.project, v.subject_name, v.creation
			order by v.creation asc, v.name asc""", {**params.parameters, "cc_confirmed": CONFIRMED}, as_dict=True)
		out = {}
		for r in rows:
			if r.project in out:
				out[r.project]["count"] += 1
				continue
			days = date_diff(nowdate(), r.creation)
			people = r.people or _("the client")
			age = _("today") if days < 1 else _("1 day") if days == 1 else _("{0} days").format(days)
			out[r.project] = {"count": 1, "request": r.name, "days": days,
				"text": _("Waiting on {0}: {1}, {2}").format(people, r.subject_name, age)}
		return out

	# --- rows --------------------------------------------------------------------------------------------------------

	def row(self, t, count, top, mentioned: set) -> dict:
		new, in_threads = count or (0, 0)
		in_thread = bool(top) and top.thread != t.name
		row = {"room": t.name, "project": t.project, "audience": t.audience,
			"title": read.title_for(ViewCtx(user=self.viewer, thread=t, staff=self.staff, memo=self.memo), t),
			"unread": new, "in_threads": in_threads,
			"around": (top.cc_root if in_thread else top.name) if top else None,
			"open_thread": top.thread if in_thread else None}
		if self.staff:
			row.update(needs_reply=bool(top) and top.cc_type == "Website User", mentions=t.name in mentioned,
				waiting=self.on_clients.get(t.project) if t.audience == "Client" else None)
		return row

	def ordered(self, rows: list, rooms: list, newest: dict) -> list:
		"""Projects by their latest line (else their rooms' creation), newest first; in a project, AUDIENCE_ORDER."""
		when = {t.name: get_datetime((newest.get(t.name) or t).creation) for t in rooms}
		latest = {}
		for t in rooms:
			latest[t.project] = max(latest.get(t.project, when[t.name]), when[t.name])
		rank = {a: i for i, a in enumerate(AUDIENCE_ORDER)}
		return sorted(rows, key=lambda r: (-latest[r["project"]].timestamp(), r["project"],
			rank.get(r["audience"], len(rank)), r["room"]))

	def keeps(self, row: dict) -> bool:
		if self.show == "unread":
			return bool(row["unread"] or row["in_threads"])
		if self.show in ("reply", "mentions", "waiting"):
			return bool(row[{"reply": "needs_reply"}.get(self.show, self.show)])
		return True

	def totals(self, rows: list) -> dict:
		out = {"rooms": len(rows), "unread": sum(1 for r in rows if r["unread"] or r["in_threads"])}
		if self.staff:
			out.update(reply=sum(1 for r in rows if r["needs_reply"]), mentions=sum(1 for r in rows if r["mentions"]),
				waiting=sum(1 for r in rows if r["waiting"]), by_project=self.by_project(rows))
		return out

	@staticmethod
	def by_project(rows: list) -> dict:
		"""{project: rooms with something new}: the top bar keeps its count per project (store.js), from this read and
		the frame's (unread_by_project), the same rule."""
		out = {p: 0 for p in dict.fromkeys(r["project"] for r in rows)}
		for r in rows:
			if r["unread"] or r["in_threads"]:
				out[r["project"]] += 1
		return out

	def draw(self, page: list, newest: dict) -> None:
		"""Each row's ``last``: one present() per audience on the page, with the authors read in the line's query. The
		line is who, the first line, the kind and when: it draws no part cards (a file shows as kind Files, and the
		line is never a System card), so present() asks nothing more and the cost does not grow with the rooms."""
		tops = {r["room"]: newest[r["room"]] for r in page if r["room"] in newest}
		people = {t.author: {"full_name": t.cc_full_name, "user_image": t.cc_image, "user_type": t.cc_type}
			for t in tops.values()}
		drawn = {}
		for audience in dict.fromkeys(r["audience"] for r in page if r["room"] in tops):
			ctx = ViewCtx(user=self.viewer, thread=frappe._dict(audience=audience, project=None), staff=self.staff,
				memo=self.memo)
			rows = [frappe._dict(t, kind=chat_view.kind_of(t), file=None) for t in
				(tops[r["room"]] for r in page if r["audience"] == audience and r["room"] in tops)]
			drawn.update({m["name"]: m for m in chat_view.present(ctx, rows, people=people)})
		for r in page:
			r["last"] = drawn.get(tops[r["room"]].name) if r["room"] in tops else None


def _project_out(p) -> dict:
	return {"name": p.name, "title": p.project_name, "status": p.status}


def unread_by_project(user: str, projects: list[str]) -> dict:
	"""{project: rooms with something new}, for the top bar's first count (P3-74; the workspace frame carries it, so no
	app-wide chat host reads the inbox). The inbox's own rule (room messages by others after the read state, and
	replies in the threads the user follows; never System cards, but a confirmed approver's Open approval cards, P3-78, N11) for
	the user's member projects among ``projects``, in one grouped read over the user's own visible messages."""
	member = set(allowed_projects(user))
	projects = [p for p in projects if p in member]
	if not projects:
		return {}
	params = NamedParameterWrapper()
	visible = read.counted_sql(user, {"project": ["in", projects], "author": ["!=", user]},
		["name", "thread", "creation", "project"], params)
	rows = frappe.db.sql(f"""select m.project, count(distinct coalesce(t.in_room, t.name))
		from ({visible}) m join `tabDiscuss Thread` t on t.name = m.thread
		left join `tabDiscuss Follow` f on t.in_room is not null and f.thread = m.thread and f.user = %(cc_user)s
		left join `tabDiscuss Read State` r on r.thread = m.thread and r.user = %(cc_user)s
		where (t.room_key is not null or f.name is not null)
			and (r.last_read_on is null or m.creation > r.last_read_on)
		group by m.project""", {**params.parameters, "cc_user": user})
	return {p: cint(n) for p, n in rows}
