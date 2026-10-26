"""What a chat read answers (design §13.1 S4): ``present`` draws visible rows as messages, ``respond`` is the one exit.

A message is CORE_KEYS plus ``parts`` (registered keys) plus ``can`` (D-393). respond, in order:
1. refuses a message key outside CORE_KEYS, or a parts key that no part registered (fail closed);
2. drops each part item whose ``_ref`` the viewer cannot read and, for the staff preview, the caller too; with a
   caller it also drops each message the caller cannot read;
3. refuses a ``_ref`` below the first item level;
4. strips every key that starts with ``_``, at any depth: no File id leaves (P3-07).
The inbox's ``rooms`` (P3-74, §14.6) are checked the same way: a row key outside ROOM_KEYS refuses, a staff key in a
client's row refuses, and each row's ``last`` message goes through the message checks above. Its ``totals`` are
checked against TOTAL_KEYS the same way: no staff count reaches a client.
"""

import html

import frappe
from frappe.utils import get_datetime, pretty_date, strip_html

from construction_core.discuss import parts
from construction_core.permissions import is_client

CORE_KEYS = frozenset({"name", "author", "text", "when", "creation", "mine", "kind", "staff_only", "pinned",
	"seen_by", "parts", "can", "from_client",  # from_client: staff only, for "Discuss with team" (P3-64)
	"edited", "removed", "agreed"})  # P3-68 (D-410, D-373); reply_to is cut: replies are threads (D-419)
MESSAGE_LISTS = ("messages", "pinned")
ROOM_LISTS = ("rooms",)
STAFF_ROOM_KEYS = frozenset({"needs_reply", "mentions", "waiting"})  # waiting: P3-80  # staff only (§14.4's inbox row)
ROOM_KEYS = frozenset({"room", "project", "audience", "title", "unread", "in_threads", "last", "around",
	"open_thread"}) | STAFF_ROOM_KEYS
STAFF_TOTAL_KEYS = frozenset({"reply", "mentions", "waiting", "by_project"})  # the inbox's staff counts (§14.4's inbox row)
TOTAL_KEYS = frozenset({"rooms", "unread"}) | STAFF_TOTAL_KEYS
STAFF_ACTIONS = ("pin", "edit", "remove", "agree", "history")  # P3-68: the order actions.can() returns


def present(ctx, rows: list, reads: list | None = None, people: dict | None = None) -> list[dict]:
	"""Rows from visible_messages as ``ctx.user`` sees them. ``reads``: the thread's read states, for staff "Seen by"
	when the project shows it (D-099); None leaves it out. ``people``: {user: User row} read with the rows (the inbox,
	so its query count does not grow with its authors); None reads each author from the cache."""
	from construction_core.discuss.actions import can  # here: actions draws its answers with present()
	from construction_core.discuss.parts.pointer import HIDDEN

	shown = [r for r in rows if not r.get("removed")]  # P3-68: a removed message shows no part, so none reads it
	built = {p.key: p.build(ctx, shown) for p in parts.PARTS if ctx.thread.audience in p.audiences}
	hidden = ctx.memo.get(HIDDEN) or set()  # P3-69: a design event card whose record this viewer cannot read now
	out = []
	for r in rows:
		if r.name in hidden:
			continue
		removed = bool(r.get("removed"))
		m = {"name": r.name, "author": person(r.author, people), "text": "" if removed else plain(r.content),
			"when": pretty_date(r.creation), "creation": str(r.creation), "mine": r.author == ctx.user,
			"kind": kind_of(r), "parts": {k: v[r.name] for k, v in built.items() if r.name in v},
			"can": can(ctx, r), "edited": bool(r.get("edited")), "removed": removed, "agreed": bool(r.get("agreed"))}
		if ctx.staff:
			m.update(staff_only=bool(r.staff_only), pinned=bool(r.get("pinned")), from_client=_client(ctx, r.author, people))
		if reads is not None:
			m["seen_by"] = [person(s.user) for s in reads if s.user != r.author and s.last_read_on
				and get_datetime(s.last_read_on) >= get_datetime(r.creation)]
		out.append(m)
	return out


def _client(ctx, user: str, people: dict | None = None) -> bool:
	if people and user in people:
		return people[user].get("user_type") == "Website User"  # is_client's own test, on the row read with the page
	key = ("is_client", user)
	if key not in ctx.memo:
		ctx.memo[key] = is_client(user)
	return ctx.memo[key]


def respond(view: dict, viewer: str, caller: str | None = None, memo: dict | None = None) -> dict:
	memo = {} if memo is None else memo
	known = set(parts.by_key())
	for key in MESSAGE_LISTS:
		if key in view:
			view[key] = [_checked(m, viewer, caller, known, memo) for m in view[key]
				if caller is None or _reads(memo, "Discuss Message", m["name"], caller)]
	for key in ROOM_LISTS:
		if key in view:
			view[key] = [_room_checked(r, viewer, caller, known, memo) for r in view[key]]
	if "totals" in view:
		_closed_keys("inbox total", view["totals"], TOTAL_KEYS, STAFF_TOTAL_KEYS, viewer)
	return strip(view)


def _room_checked(row: dict, viewer: str, caller, known: set, memo: dict) -> dict:
	_closed_keys("inbox row", row, ROOM_KEYS, STAFF_ROOM_KEYS, viewer)
	last = row.get("last")
	if last and caller is not None and not _reads(memo, "Discuss Message", last["name"], caller):
		row["last"] = last = None
	if last:
		row["last"] = _checked(last, viewer, caller, known, memo)
	return row


def _closed_keys(what: str, value: dict, allowed: frozenset, staff: frozenset, viewer: str) -> None:
	"""Fail closed: a key outside ``allowed``, or a staff key for a client, refuses the whole answer."""
	if set(value) - allowed:
		raise frappe.ValidationError(f"An {what} cannot carry {sorted(set(value) - allowed)}")
	if set(value) & staff and is_client(viewer):
		raise frappe.ValidationError(f"A client's {what} cannot carry {sorted(set(value) & staff)}")


def strip(value):
	if isinstance(value, dict):
		return {k: strip(v) for k, v in value.items() if not (isinstance(k, str) and k.startswith("_"))}
	if isinstance(value, list | tuple):
		return [strip(v) for v in value]
	return value


def person(user: str, people: dict | None = None) -> dict:
	row = people[user] if people and user in people else \
		frappe.get_cached_value("User", user, ["full_name", "user_image"], as_dict=True) or {}
	return {"user": user, "name": row.get("full_name") or user, "image": row.get("user_image")}


def plain(content) -> str:
	# Frappe stores text fields sanitised as HTML; the pages show plain text and escape it themselves.
	return html.unescape(strip_html(content or ""))


def kind_of(row) -> str:
	"""Messages from before the kind field read as Files when they carry a file, else Text (plan §3.1)."""
	return row.get("kind") or ("Files" if row.get("file") else "Text")


def _checked(m: dict, viewer: str, caller, known: set, memo: dict) -> dict:
	if set(m) - CORE_KEYS:
		raise frappe.ValidationError(f"A chat message cannot carry {sorted(set(m) - CORE_KEYS)}")
	values = m.get("parts") or {}
	if set(values) - known:
		raise frappe.ValidationError(f"A chat message cannot carry the part {sorted(set(values) - known)}")
	kept = {}
	for key, value in values.items():
		value = _readable(value, viewer, caller, memo)
		if value:
			kept[key] = value
	if "parts" in m:
		m["parts"] = kept
	return m


def _readable(value, viewer: str, caller, memo: dict):
	"""A part's value is a list of items or one item. An item whose ``_ref`` a reader cannot open is dropped, so it
	looks exactly like a deleted one (rule 2)."""
	items = value if isinstance(value, list) else [value]
	kept = [i for i in items if _item_readable(i, viewer, caller, memo)]
	return kept if isinstance(value, list) else (kept[0] if kept else None)


def _item_readable(item, viewer: str, caller, memo: dict) -> bool:
	if not isinstance(item, dict):
		return True
	for v in item.values():
		_no_nested_ref(v)
	ref = item.get("_ref")
	if not ref:
		return True
	doctype, name = ref
	return _reads(memo, doctype, name, viewer) and (caller is None or _reads(memo, doctype, name, caller))


def _no_nested_ref(value) -> None:
	if isinstance(value, dict):
		if "_ref" in value:
			raise frappe.ValidationError("A _ref is allowed at the first item level only")
		for v in value.values():
			_no_nested_ref(v)
	elif isinstance(value, list | tuple):
		for v in value:
			_no_nested_ref(v)


def _reads(memo: dict, doctype: str, name: str, user: str) -> bool:
	key = (doctype, name, user)
	if key not in memo:
		memo[key] = bool(frappe.has_permission(doctype, "read", doc=name, user=user, throw=False))
	return memo[key]
