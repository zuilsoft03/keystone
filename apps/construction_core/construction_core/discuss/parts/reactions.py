"""The reactions part (design §3.8; P3-68): the fixed reaction sets, the summary each message keeps, and the endpoint.

**The sets** (L-6, PD-11, hub §7): staff 👍 Noted, ✅ Done, 👀 Looking, ❓ Question; clients 👍 Noted and ❓ Question only,
so no client reaction reads as an approval. The set is the sender's: a client cannot add Done or Looking anywhere;
staff may add them in the Client room too (who reacted is drawn with it). Partners take the staff set (P3-32).

**Rows and the summary.** One Discuss Reaction row per (message, user, reaction), made and removed by ``react`` only.
The message keeps a summary, ``reactions`` = {reaction: [user, ...]}, recounted from the rows after the commit (D-177,
rule 6: a request never writes a shared count), so a page draws every reaction with no query (the lead's query budget),
and the viewer's own reactions come from the same summary. Names are read from the cache, like authors. The people a
summary names are readers of the message's room, so no client sees a partner or the reverse (L-17).

**The endpoint** is a chat action (discuss.actions): the parent message as the viewer, the portal checks for a client,
never on a removed message or a card. Its answer is the message with the summary as it will be (read in the request);
the readers are told when the job has recounted it.
"""

import json
from functools import partial

import frappe
from frappe import _
from frappe.utils import cint

from construction_core.discuss import live, rows
from construction_core.discuss import view as chat_view
from construction_core.discuss.actions import chat_action, first_wins
from construction_core.discuss.registry import Part, ViewCtx

ORDER = ("noted", "done", "looking", "question")
SETS = {"staff": frozenset(ORDER), "client": frozenset({"noted", "question"})}
FRESH = "reactions fresh"  # ctx.memo key: the summary an action's own answer draws


def summary(raw) -> dict:
	try:
		value = json.loads(raw) if raw else {}
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}


# --- the cards ------------------------------------------------------------------------------------------------------


def build(ctx: ViewCtx, rows_: list) -> dict:
	"""{message: [{key, count, people, mine}]} in the fixed order, from each row's summary; no query."""
	out = {}
	for r in rows_:
		got = ctx.memo.get((FRESH, r.name))
		got = summary(r.get("reactions")) if got is None else got
		items = [{"key": k, "count": len(got[k]), "people": [chat_view.person(u) for u in got[k]],
			"mine": ctx.user in got[k]} for k in ORDER if isinstance(got.get(k), list) and got[k]]
		if items:
			out[r.name] = items
	return out


def capable(ctx: ViewCtx, thread) -> bool:
	return thread.status != "Locked" and thread.audience in PART.audiences


# --- the endpoint ---------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
@chat_action("reactions")
def react(message: str, reaction: str, on: int | str = 1, *, _ctx=None, _row=None) -> None:
	"""Add (``on`` 1) or take back (``on`` 0) the caller's reaction; adding one already there changes nothing."""
	sender = "staff" if _ctx.staff else "client"
	if reaction not in SETS[sender]:
		frappe.throw(_("This reaction cannot be used here"))
	mine = {"message": _row.name, "user": _ctx.user, "reaction": reaction}
	there = frappe.db.exists("Discuss Reaction", mine)
	if cint(on) and not there:
		first_wins(lambda: rows.insert("Discuss Reaction", {"user": _ctx.user, "reaction": reaction},
			thread=_row.thread, message=_row.name))
	elif not cint(on) and there:
		frappe.db.delete("Discuss Reaction", mine)  # the server's own removal (ChatRow)
	_ctx.memo[(FRESH, _row.name)] = count(_row.name)
	queue_recount(_row.name)


def count(message: str) -> dict:
	"""{reaction: [user]} from the rows, oldest first."""
	out = {}
	for r in frappe.get_all("Discuss Reaction", filters={"message": message}, fields=["user", "reaction"],
			order_by="creation asc, name asc"):
		out.setdefault(r.reaction, []).append(r.user)
	return {k: out[k] for k in ORDER if k in out}


def queue_recount(message: str) -> None:
	"""The summary moves after the commit, in a short job (send.queue_counters' pattern)."""
	frappe.db.after_commit.add(partial(_queue, message))


def _queue(message: str) -> None:
	if frappe.in_test:
		recount(message)
		return
	try:
		frappe.enqueue("construction_core.discuss.parts.reactions.recount", queue="short", message=message)
	except Exception:
		frappe.logger("construction_core").exception("The chat reaction summary was not queued")


def recount(message: str) -> None:
	"""Write the summary from the rows; a lost 1020 race is tried once more. Then the readers are told, by ids."""
	try:
		_write(message)
	except frappe.QueryDeadlockError:
		frappe.db.rollback()
		_write(message)
	row = frappe.db.get_value("Discuss Message", message, ["name", "thread", "project", "audience", "staff_only"],
		as_dict=True)
	if row:
		live.message_changed(row, "reactions")


def _write(message: str) -> None:
	if frappe.db.exists("Discuss Message", message):
		got = count(message)
		frappe.db.set_value("Discuss Message", message, "reactions", json.dumps(got) if got else None,
			update_modified=False)


PART = Part(key="reactions", audiences=frozenset({"Internal", "Client"}), senders=frozenset(), implies_kind=None,
	claim=None, build=build, capable=capable)
