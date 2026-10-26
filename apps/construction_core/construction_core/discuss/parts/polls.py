"""The polls part (design §3.7; P3-68; D-362, D-363): a question, 2 to 10 options, one choice or several, and the votes.

**The send** (staff only): ``parts: {"polls": {"question", "options": [{"text", "picture"}], "multiple", "anonymous",
"closes_on"}}``. ``claim`` checks the shape: a question, 2 to 10 options each with text or a picture, an optional close
time in the future. **Anonymous** polls are for Internal threads only (partner rooms from P3-32): a Client thread's poll
is named, and the card there says it is not an approval (QH-D). **A picture** is a photo the same message carries: the
sender stages it like any file (a project file in a Client room goes as a checked copy, "Share and send"), lists it in
the message's ``attachments`` part, and names that attachment here. So a picture is checked like any attachment, and
its card comes from the attachments part's one page read (respond() allows ``_ref`` at the first item level only).
``write`` makes the Discuss Poll row after the insert.

**Votes** (``vote``): one row per person and option, unique (poll, user, slot), the slot 'single' in a one-choice
poll; a vote can change, or be taken back with no options, until the poll closes (its close time, or ``close`` by its
author or the project's manager, SEC-17). The vote rows are System Manager only, so an anonymous poll names no voter.

**The card** (``build``): the page's polls and the viewer's own votes in one query, whatever the number of polls; the
tallies are on the poll row (``tally``, and ``voters`` for a named poll), recounted after the commit (rule 6), so a card
costs nothing more. Each option carries its votes and, in a named poll, who voted (names from the cache).
"""

import json
from functools import partial

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from construction_core.discuss import live, rows
from construction_core.discuss import view as chat_view
from construction_core.discuss.actions import changed, chat_action, first_wins, manages
from construction_core.discuss.registry import Part, SendCtx, ViewCtx

MIN_OPTIONS, MAX_OPTIONS = 2, 10
MAX_QUESTION, MAX_OPTION = 300, 200
MAX_OPEN_DAYS = 366
KEYS = {"question", "options", "multiple", "anonymous", "closes_on"}
ANONYMOUS_IN = frozenset({"Internal"})  # QH-D: never in a Client thread
FRESH = "polls fresh"  # ctx.memo key: the tallies an action's own answer draws
SINGLE = "single"
SENDING = "cc_discuss_write"  # send.CLAIM: the whole send this part is claimed in


# --- the send -------------------------------------------------------------------------------------------------------


def claim(ctx: SendCtx, value) -> dict:
	"""The poll, checked and normalised; no writes."""
	if not isinstance(value, dict) or set(value) - KEYS:
		frappe.throw(_("The poll is not valid"))
	question = _text(value.get("question"), MAX_QUESTION)
	options = value.get("options")
	if not question or not isinstance(options, list) or not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
		frappe.throw(_("A poll has a question and {0} to {1} options").format(MIN_OPTIONS, MAX_OPTIONS))
	anonymous = bool(cint(value.get("anonymous")))
	if anonymous and (ctx.staff_only or ctx.thread.audience not in ANONYMOUS_IN):
		frappe.throw(_("A poll in a client conversation shows who voted"), frappe.PermissionError)
	pictures = _pictures([o.get("picture") for o in options if isinstance(o, dict) and o.get("picture")])
	out = []
	for i, o in enumerate(options):
		if not isinstance(o, dict) or set(o) - {"text", "picture"}:
			frappe.throw(_("The poll is not valid"))
		text, picture = _text(o.get("text"), MAX_OPTION), o.get("picture") or None
		if not (text or picture) or (picture and picture not in pictures):
			frappe.throw(_("Each option needs words or a picture"))
		out.append({"key": str(i + 1), "text": text, "picture": picture})
	return {"question": question, "options": out, "multiple": bool(cint(value.get("multiple"))),
		"anonymous": anonymous, "closes_on": _closes_on(value.get("closes_on"))}


def _text(value, limit: int) -> str:
	text = value.strip() if isinstance(value, str) else ""
	if len(text) > limit:
		frappe.throw(_("A poll's words are at most {0} characters").format(limit))
	return text


def _pictures(ids: list) -> set:
	"""The pictures must be photos this same send carries in its attachments part, each used once."""
	if not ids:
		return set()
	sending = frappe.flags.get(SENDING)
	carried = (sending.parts or {}).get("attachments") if sending else None
	if (not isinstance(carried, list) or len(set(ids)) != len(ids)
			or not all(isinstance(i, str) and i in carried for i in ids)):
		frappe.throw(_("A poll's picture must be a photo sent with it"))
	kinds = dict(frappe.get_all("Discuss Attachment", filters={"name": ["in", ids]}, fields=["name", "kind"],
		as_list=True))
	if any(kinds.get(i) != "photo" for i in ids):
		frappe.throw(_("A poll's picture must be a photo sent with it"))
	return set(ids)


def _closes_on(value):
	if value in (None, ""):
		return None
	try:
		when = get_datetime(value) if isinstance(value, str) else None
	except Exception:
		when = None
	if not when or when <= now_datetime() or when > add_to_date(now_datetime(), days=MAX_OPEN_DAYS):
		frappe.throw(_("Choose a close time in the coming year"))
	return when.replace(tzinfo=None)


def write(doc, value: dict) -> None:
	rows.insert("Discuss Poll", {"question": value["question"], "options": json.dumps(value["options"]),
		"multiple": int(value["multiple"]), "anonymous": int(value["anonymous"]), "closes_on": value["closes_on"],
		"voter_count": 0}, thread=doc.thread, message=doc.name)


# --- the card -------------------------------------------------------------------------------------------------------


def build(ctx: ViewCtx, rows_: list) -> dict:
	"""{message: card} for the page's polls, in one query with the viewer's own votes."""
	if not ctx.thread.get("name"):
		return {}  # the inbox's last line draws no card
	authors = {r.name: r.author for r in rows_ if r.get("kind") == "Poll"}
	if not authors:
		return {}
	found = frappe.db.sql("""select p.name, p.message, p.question, p.options, p.multiple, p.anonymous, p.closes_on,
			p.closed_on, p.tally, p.voters, p.voter_count, group_concat(v.option separator '\n') as mine
		from `tabDiscuss Poll` p
		left join `tabDiscuss Poll Vote` v on v.poll = p.name and v.user = %(cc_user)s
		where p.message in %(cc_names)s group by p.name""", {"cc_user": ctx.user, "cc_names": tuple(authors)},
		as_dict=True)
	return {p.message: card(ctx, p, authors[p.message]) for p in found}


def card(ctx: ViewCtx, p, author: str) -> dict:
	fresh = ctx.memo.get((FRESH, p.message)) or {}
	tally = fresh.get("tally", _json(p.tally))
	voters = fresh.get("voters", _json(p.voters))
	mine = set((p.mine or "").split("\n")) - {""}
	closed = is_closed(p)
	options = []
	for o in _json(p.options, []):
		item = {"key": o["key"], "text": o.get("text") or "", "picture": o.get("picture"),
			"votes": cint(tally.get(o["key"])), "mine": o["key"] in mine}
		if not p.anonymous:
			item["voters"] = [chat_view.person(u) for u in voters.get(o["key"]) or []]
		options.append(item)
	open_ = not closed and ctx.thread.get("status") != "Locked"
	return {"question": p.question, "multiple": bool(p.multiple), "anonymous": bool(p.anonymous),
		"closes_on": str(p.closes_on) if p.closes_on else None, "closed": closed,
		"people": cint(fresh.get("voter_count", p.voter_count)), "options": options, "can_vote": open_,
		"can_close": open_ and ctx.staff and (author == ctx.user or manages(ctx))}


def is_closed(p) -> bool:
	return bool(p.closed_on) or bool(p.closes_on and get_datetime(p.closes_on) <= now_datetime())


def _json(raw, empty=None):
	try:
		value = json.loads(raw) if raw else None
	except (TypeError, ValueError):
		value = None
	return value if value is not None else ({} if empty is None else empty)


def capable(ctx: ViewCtx, thread) -> bool:
	"""Staff make polls in an open thread (§3.7)."""
	return ctx.staff and thread.status != "Locked" and thread.audience in PART.audiences


# --- the endpoints --------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
@chat_action("polls")
def vote(message: str, options=None, *, _ctx=None, _row=None) -> None:
	"""The caller's vote: the option keys they choose now (one in a one-choice poll; none takes the vote back)."""
	p = poll_of(_row.name)
	if is_closed(p):
		frappe.throw(_("This poll is closed"))
	keys = _choice(p, options)

	def write():
		frappe.db.delete("Discuss Poll Vote", {"poll": p.name, "user": _ctx.user})  # the server's own removal (ChatRow)
		for key in keys:
			rows.insert("Discuss Poll Vote", {"poll": p.name, "user": _ctx.user, "option": key,
				"slot": key if p.multiple else SINGLE}, thread=_row.thread, message=_row.name)

	first_wins(write)  # the unique key is the one-vote rule; no lock on the poll row, which the recount writes
	_ctx.memo[(FRESH, _row.name)] = tally(p)
	queue_recount(p.name)


@frappe.whitelist(methods=["POST"])
@chat_action("polls")
def close(message: str, *, _ctx=None, _row=None) -> None:
	"""Close the poll now: its author or the project's manager (SEC-17)."""
	p = poll_of(_row.name)
	if not (_ctx.staff and (_row.author == _ctx.user or manages(_ctx))):
		frappe.throw(_("Only the poll's author or the project's manager can close it"), frappe.PermissionError)
	if not p.closed_on:
		frappe.db.set_value("Discuss Poll", p.name, {"closed_on": now_datetime(), "closed_by": _ctx.user},
			update_modified=False)
	changed(_row, "polls")


def poll_of(message: str):
	"""The message's poll; else "Not found"."""
	got = frappe.db.sql("""select name, message, options, multiple, anonymous, closes_on, closed_on
		from `tabDiscuss Poll` where message = %s""", message, as_dict=True)
	if not got:
		raise frappe.DoesNotExistError(_("Not found"))
	return got[0]


def _choice(p, options) -> list:
	try:
		options = frappe.parse_json(options) if isinstance(options, str) else options
	except ValueError:
		options = None
	options = [] if options is None else options
	valid = [o["key"] for o in _json(p.options, [])]
	if (not isinstance(options, list) or not all(isinstance(o, str) and o in valid for o in options)
			or len(set(options)) != len(options) or (not p.multiple and len(options) > 1)):
		frappe.throw(_("Choose from the poll's options"))
	return options


def tally(p) -> dict:
	"""{tally, voters, voter_count} from the vote rows; ``voters`` empty for an anonymous poll."""
	counts, voters, people = {}, {}, set()
	for v in frappe.get_all("Discuss Poll Vote", filters={"poll": p.name}, fields=["user", "option"],
			order_by="creation asc, name asc"):
		counts[v.option] = counts.get(v.option, 0) + 1
		voters.setdefault(v.option, []).append(v.user)
		people.add(v.user)
	return {"tally": counts, "voters": {} if p.anonymous else voters, "voter_count": len(people)}


def queue_recount(poll: str) -> None:
	"""The tallies move after the commit, in a short job (send.queue_counters' pattern, rule 6)."""
	frappe.db.after_commit.add(partial(_queue, poll))


def _queue(poll: str) -> None:
	if frappe.in_test:
		recount(poll)
		return
	try:
		frappe.enqueue("construction_core.discuss.parts.polls.recount", queue="short", poll=poll)
	except Exception:
		frappe.logger("construction_core").exception("The chat poll tallies were not queued")


def recount(poll: str) -> None:
	"""Write the tallies from the vote rows; a lost 1020 race is tried once more. Then the readers are told, by ids."""
	try:
		message = _write(poll)
	except frappe.QueryDeadlockError:
		frappe.db.rollback()
		message = _write(poll)
	row = frappe.db.get_value("Discuss Message", message, ["name", "thread", "project", "audience", "staff_only"],
		as_dict=True) if message else None
	if row:
		live.message_changed(row, "polls")


def _write(poll: str) -> str | None:
	p = frappe.db.get_value("Discuss Poll", poll, ["name", "message", "anonymous"], as_dict=True)
	if not p:
		return None
	got = tally(p)
	frappe.db.set_value("Discuss Poll", poll, {"tally": json.dumps(got["tally"]),
		"voters": json.dumps(got["voters"]) if got["voters"] else None, "voter_count": got["voter_count"]},
		update_modified=False)
	return p.message


PART = Part(key="polls", audiences=frozenset({"Internal", "Client"}), senders=frozenset({"staff"}),
	implies_kind="Poll", claim=claim, build=build, capable=capable, write=write)
