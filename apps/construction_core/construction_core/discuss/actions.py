"""Message actions (D-395, design §13.0 {DX-d}, §3.7, §3.8): react, vote, close, edit, remove and Agreed.

Each action is one endpoint in its part's module (or in discuss.edit), whitelisted as usual and wrapped by
``chat_action``, which branches on the session's account kind and keeps every guarantee in one place:

- **The parent message, as the viewer** (SEC-7): it is read with Frappe's list as the caller, so a message of a thread
  they cannot read (a staff-only note, the Team room, another project) answers exactly like a missing one.
- **A client** passes the portal's checks too (rule 3: portal on, Discussion on, member, Client thread, not Locked).
- **Never** on a removed message or a System card (a mirror follows its reply, §14.2), nor in a Locked thread.
- **A rate limit** per user and minute, its own bucket beside the send's.
- **One answer**: the message as the caller now reads it, through present() and respond() (S4). A write that loses a
  race (MariaDB 1020) is taken back whole and tried once more on a fresh snapshot: an action writes nothing before.

``can`` says which of the author's and the manager's actions a viewer gets on a message: edit (the author, 15 minutes,
D-368), remove (the author for 15 minutes, the project's manager at any time, D-369), agree (staff who are the author
or the manager, on a Client-room message, D-373), history (staff, an edited message). Reacting is a capability of the
thread (the reactions part), voting and closing are on the poll card. "The project's manager" is the viewer's Project
Member role on that project, never the global Construction Manager role (SEC-17); System Managers moderate too.

The Agreed mark (D-373) is here: staff only, never a client approval. ``agreed`` lists a thread's agreed messages,
newest first, for the top of the conversation.
"""

import functools
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from construction_core.discuss import checks, live
from construction_core.discuss.registry import sender_of
from construction_core.permissions import _bypass, is_client, refuse_closed, switches_once

WINDOW = timedelta(minutes=15)  # the author's edit and remove (D-368, D-369)
RATES = {"client": 60, "staff": 240}  # actions per user per minute (SEC-21's flood row)
RATE_WINDOW = 60
MANAGER = "Project Manager"  # Project Member.cc_workspace_role
# What an action reads of its message besides read.FIELDS, as the viewer: permlevel 0, so a client reads them (D-397)
TARGET_FIELDS = ("thread", "project", "audience")
# read and view import the parts, and the parts import this module for chat_action: they are imported where used.


def chat_action(part: str):
	"""Wrap an endpoint ``fn(message, ..., *, _ctx, _row)``; the wrapper reads the message and passes both itself, so a
	request value for ``_ctx`` or ``_row`` is never used. ``part``: what the change event names."""

	def wrap(fn):
		@functools.wraps(fn)
		def endpoint(message, *args, **kwargs):
			kwargs.pop("_ctx", None)
			kwargs.pop("_row", None)
			viewer = frappe.session.user
			count(viewer)

			def once():
				with switches_once():
					ctx, row = target(viewer, message)
					fn(message, *args, _ctx=ctx, _row=row, **kwargs)
					return answer(ctx, row.name)

			try:
				return once()
			except frappe.QueryDeadlockError:
				frappe.db.rollback()
				return once()

		endpoint.cc_chat_action = part
		return endpoint

	return wrap


def target(viewer: str, name):
	"""(ViewCtx, message row) of a message the viewer may act on; one refusal for missing and unreadable."""
	from construction_core.discuss import read

	rows = frappe.get_list("Discuss Message", filters={"name": name}, fields=[*read.FIELDS, *TARGET_FIELDS], limit=1,
		user=viewer) if isinstance(name, str) and name else None
	if not rows:
		raise frappe.DoesNotExistError(_("Not found"))
	row = rows[0]
	t = read.thread_for(viewer, row.thread)
	if sender_of(viewer) == "client":
		checks.client_send(frappe.get_doc("Discuss Thread", t.name))
	elif t.status == "Locked":
		frappe.throw(_("This thread is locked"))
	refuse_closed(t.project)  # P3-59 (P3-68 audit C3): react, vote, close, edit, remove and agree too, for everyone
	if row.removed or row.kind == "System":
		frappe.throw(_("This message cannot be changed"), frappe.PermissionError)
	return read.context(viewer, t), row


def answer(ctx, name: str) -> dict | None:
	"""The message as the caller reads it now, through the one exit."""
	from construction_core.discuss import read
	from construction_core.discuss import view as chat_view

	rows = frappe.get_list("Discuss Message", filters={"name": name},
		fields=list(read.STAFF_FIELDS if ctx.staff else read.FIELDS), limit=1, user=ctx.user)
	out = chat_view.respond({"messages": chat_view.present(ctx, rows)}, ctx.user, memo=ctx.memo)
	return out["messages"][0] if out["messages"] else None


def can(ctx, r) -> list[str]:
	"""The message actions ``ctx.user`` gets on row ``r`` (MESSAGE_ACTIONS ids). No query: the role is read from the
	cached project."""
	if r.get("removed"):
		return []
	out = ["pin"] if ctx.staff and not r.staff_only else []  # pins are on shared messages
	if (r.get("kind") == "System" or ctx.thread.get("status") == "Locked" or not ctx.thread.get("name")
			or not ctx.thread.get("project")):
		return out  # the inbox's last line (no thread) is no place to act
	mine, fresh = r.author == ctx.user, in_window(r.creation)
	if mine and fresh:
		out.append("edit")
	if (mine and fresh) or manages(ctx):
		out.append("remove")
	if ctx.staff and ctx.thread.audience == "Client" and not r.staff_only and (mine or manages(ctx)):
		out.append("agree")
	if ctx.staff and r.get("edited"):
		out.append("history")
	return out


def in_window(creation) -> bool:
	return bool(creation) and now_datetime() - get_datetime(creation) <= WINDOW


def manages(ctx, user: str | None = None) -> bool:
	"""The viewer is the project's manager (their Project Member role there), or a System Manager."""
	user = user or ctx.user
	key = ("manages", ctx.thread.project, user)
	if key not in ctx.memo:
		ctx.memo[key] = _bypass(user) or is_manager(user, ctx.thread.project)
	return ctx.memo[key]


def is_manager(user: str, project: str | None) -> bool:
	if not project or is_client(user):  # a client's member row never makes them the manager (audit C2)
		return False
	try:
		members = frappe.get_cached_doc("Construction Project", project).get("users") or []
	except frappe.DoesNotExistError:
		frappe.clear_last_message()
		return False
	return any(m.user == user and m.get("cc_workspace_role") == MANAGER for m in members)


def first_wins(write) -> bool:
	"""Run a write that a second click of the same person may have made already (react, vote): on the unique key it is
	taken back to a savepoint and the other click's rows stand, so a double submit answers normally (False)."""
	point = "cc_act_" + frappe.generate_hash(length=8)
	messages = len(frappe.local.message_log)
	frappe.db.savepoint(point)
	try:
		write()
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		del frappe.local.message_log[messages:]  # Frappe's "must be unique" line is not this answer
		frappe.db.rollback(save_point=point)
		return False
	frappe.db.release_savepoint(point)
	return True


def changed(row, part: str) -> None:
	"""Tell the message's readers, by ids after the commit, and the readers of each card that draws it: its room mirror
	and the Team root card about it (§14.2), whose readers are their own."""
	live.message_changed(row, part)
	for card in drawn_by(row.name):
		live.message_changed(card, part)


def drawn_by(name: str) -> list:
	"""The System messages whose pointer names this message: its room mirror, and a Team root card about it."""
	cards = frappe.get_all("Discuss Pointer", filters={"target_type": "Discuss Message", "target_name": name},
		pluck="message")
	if not cards:
		return []
	return frappe.get_all("Discuss Message", filters={"name": ["in", cards], "kind": "System"},
		fields=["name", "thread", "project", "audience", "staff_only"])


def count(user: str) -> None:
	if _bypass(user):
		return
	key = frappe.cache.make_key(f"cc:discuss:act:{user}")
	done = frappe.cache.incrby(key, 1)
	if done == 1 or frappe.cache.ttl(key) == -1:
		frappe.cache.expire(key, RATE_WINDOW)
	if done > RATES[sender_of(user)]:
		frappe.throw(_("You have done many things in a short time. Wait a minute and try again."),
			frappe.RateLimitExceededError)


# --- Agreed (D-373) -------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
@chat_action("agreed")
def set_agreed(message: str, agreed: int | str = 1, *, _ctx=None, _row=None) -> None:
	"""Mark a Client-room message Agreed, or take the mark off: staff who wrote it or manage the project."""
	if "agree" not in can(_ctx, _row):
		frappe.throw(_("You cannot mark this message"), frappe.PermissionError)
	on = 1 if cint(agreed) else 0
	frappe.db.set_value("Discuss Message", _row.name, {"agreed": on, "agreed_by": _ctx.user if on else None,
		"agreed_on": now_datetime() if on else None}, update_modified=False)
	changed(_row, "agreed")


@frappe.whitelist(methods=["GET"])
def agreed(thread: str) -> dict:
	"""The thread's Agreed messages the caller reads, newest first (one page), for the top of the conversation."""
	from construction_core.discuss import read
	from construction_core.discuss import view as chat_view

	viewer = frappe.session.user
	with switches_once():
		t = read.thread_for(viewer, thread)
		ctx = read.context(viewer, t)
		rows = read.visible_messages(viewer, t.name, fields=read.STAFF_FIELDS if ctx.staff else read.FIELDS,
			only={"agreed": 1, "removed": 0})
		return chat_view.respond({"messages": chat_view.present(ctx, rows)}, viewer, memo=ctx.memo)
