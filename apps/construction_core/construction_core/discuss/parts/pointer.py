"""The pointer part (D-418, design §14.2): what a System message points at, drawn per viewer at read time.

A Discuss Pointer row names its message, a target type and the target's name (Data, never a Link). Its uses: a root
card names its thread; a room mirror names its reply; a Team root card also names the client message it is about.
The target types are registered in TARGETS, one line each, with what the part reads of a target, what a viewer sees
of it and the reader rule. P3-78's Approval Request (a card in the Client room, a line in the Team room) is drawn by
the approval part from the page's pointer rows, which this part leaves in ``ctx.memo`` (POINTERS), so a page asks the
table once; the rule that stores one is ``request_readers_read``.

- **The reader rule** (§14.4 row 2): a pointer is stored only when every reader of the message can read the target.
  The rule reads columns set once (project, audience, staff_only); the part checks it again at read time.
- **Every item carries ``_ref``**, so respond() drops one the viewer (or the preview's caller) cannot read, as for any
  part (§13.5 item 6). A target that is gone is left out like a deleted one.
- **Only the server writes a pointer**: ``add`` sets FLAG around its insert, and DiscussPointer.before_insert refuses
  any other insert, a System Manager's too.
- **Design events** (P3-69, discuss.events): a card points at a record of EVENTS, whose type names the event. It is
  drawn as the record resolver's card for this viewer, so a viewer who cannot read the record now (unshared, binned,
  its section off) gets no item, and a card left with no item is left out of their page (HIDDEN), not shown empty.
- **Cost**: build reads nothing for a page without System messages; else one pointer query, then one read as the
  viewer per target type and per type of record the cards name (ViewCtx.readable), whatever the number of cards. The
  event cards' records take one resolver query, shared with the refs part's tags on the same page (one in all).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import frappe
from frappe import _

from construction_core.discuss.registry import Part, ViewCtx
from construction_core.permissions import client_may_see

FLAG = "cc_discuss_pointer"  # set only by add()
HIDDEN = "cc_hidden_cards"  # ctx.memo: the page's event cards with nothing this viewer may read (view.present)
POINTERS = "cc_page_pointers"  # ctx.memo: the page's pointer rows, for the approval part (P3-78)
APPROVAL = "Approval Request"
# P3-69: the record types a design event points at, each with its one event (discuss.events)
EVENTS = {"Project Document": "document_published", "File": "file_revised", "Whiteboard": "board_saved"}


def every_reader_reads(message, target) -> bool:
	"""Every reader of ``message`` can read ``target``: the same project, and the project's clients may see it whenever
	they may read the message (a Client message that is no staff-only note). Partners join with P3-32."""
	if not target or target.get("project") != message.project:
		return False
	if message.audience == "Client" and not message.staff_only:
		return client_may_see(target)
	return True


def record_readers_read(message, target) -> bool:
	"""The reader rule for a design event's record: the same project, and for a Client message every client of the room
	may read it now (shared, and its portal section on)."""
	from construction_core.permissions import project_of
	from construction_core.records.resolve import audience_reads

	if not target or project_of(target) != message.project:
		return False
	if message.audience == "Client" and not message.staff_only:
		return audience_reads("Client", target)
	return True


def request_readers_read(message, target) -> bool:
	"""The reader rule for an approval request (P3-78, §3.14): the same project, and for a Client message that is no
	staff-only note every client of the room may read it now, through the request's own rule: not a Draft, decided by a
	client, the portal and the approvals section on (``target`` carries its doctype)."""
	from construction_core.records.resolve import audience_reads

	if not target or target.get("project") != message.project:
		return False
	if message.audience == "Client" and not message.staff_only:
		return audience_reads("Client", target)
	return True


def event_item(doctype: str, card: dict) -> dict:
	"""A design event as this viewer sees it: the event and the record's card (resolve.record_card or file_card)."""
	return {"_ref": card["_ref"], "type": "event", "event": EVENTS[doctype],
		"record": {k: v for k, v in card.items() if k != "_ref"}}


def thread_item(ctx: ViewCtx, t) -> dict:
	"""A root card's thread, under the title this viewer may read ("Conversation" otherwise, D-370)."""
	from construction_core.discuss.read import title_for

	return {"_ref": ("Discuss Thread", t.name), "type": "thread", "thread": t.name, "title": title_for(ctx, t)}


def thread_records(ctx: ViewCtx, threads) -> None:
	"""The records the threads' titles need, read as the viewer once per type for the page (title_for then asks the
	memo)."""
	wanted = {}
	for t in threads:
		if t.anchor_doctype and (t.anchor_doctype, t.anchor_name, ctx.user) not in ctx.memo:
			wanted.setdefault(t.anchor_doctype, []).append(t.anchor_name)
	for doctype, names in wanted.items():
		ctx.readable(doctype, names)


def message_item(ctx: ViewCtx, m) -> dict:
	"""A mirrored reply, or the client message a Team root card is about, in its latest text: an edit reaches the card
	at read time, and a removed message shows as removed with no text (P3-68)."""
	from construction_core.discuss.view import person, plain

	removed = bool(m.get("removed"))
	item = {"_ref": ("Discuss Message", m.name), "type": "message", "message": m.name, "thread": m.thread,
		"author": person(m.author), "text": "" if removed else plain(m.content),
		"kind": m.get("kind") or "Text"}  # P3-65: a photo has no text
	item.update({k: True for k in ("edited", "removed") if m.get(k)})  # additive: only when it is so
	return item


@dataclass(frozen=True)
class Target:
	doctype: str  # Discuss Pointer.target_type; target_name names a row of it
	fields: tuple  # what the part reads of a target, in one query per type and page; ``project`` for the rule
	item: Callable[[ViewCtx, Any], dict]  # what a viewer sees of one target row, with its '_ref'
	readers_read: Callable[[Any, Any], bool] = every_reader_reads  # (message, target) -> may be pointed at
	prepare: Callable[[ViewCtx, list], None] | None = None  # batched reads the items need, once per page


TARGETS = (
	Target("Discuss Thread", ("name", "project", "audience", "title", "anchor_doctype", "anchor_name", "room_key"),
		thread_item,
		prepare=thread_records),
	Target("Discuss Message", ("name", "project", "audience", "thread", "author", "content", "staff_only", "kind",
		"edited", "removed"),
		message_item),
)


def by_type() -> dict:
	return {t.doctype: t for t in TARGETS}


def add(message, target_type: str, target_name: str) -> str:
	"""Point ``message`` (a document just inserted by the server) at a target. Refused unless the reader rule holds."""
	frappe.flags[FLAG] = (message.name, target_type, target_name)
	try:
		# ignore_permissions: the server's row (D-418); before_insert still runs the reader rule.
		return frappe.get_doc({"doctype": "Discuss Pointer", "message": message.name, "target_type": target_type,
			"target_name": target_name}).insert(ignore_permissions=True).name
	finally:
		frappe.flags[FLAG] = None


def check(doc) -> None:
	"""DiscussPointer.before_insert: only add() writes a pointer, to a registered target type, and only when every
	reader of the message can read the target. The chat columns come from the message."""
	if frappe.flags.get(FLAG) != (doc.message, doc.target_type, doc.target_name):
		frappe.throw(_("References are made by the server"), frappe.PermissionError)
	target = by_type().get(doc.target_type)
	rule = target.readers_read if target else (record_readers_read if doc.target_type in EVENTS else
		request_readers_read if doc.target_type == APPROVAL else None)
	m = frappe.db.get_value("Discuss Message", doc.message, ["project", "audience", "staff_only"], as_dict=True)
	if not (rule and m and isinstance(doc.target_name, str) and frappe.db.exists(doc.target_type, doc.target_name)):
		frappe.throw(_("This reference cannot be made"))
	doc.project, doc.audience, doc.staff_only = m.project, m.audience, m.staff_only
	if not rule(m, frappe.get_doc(doc.target_type, doc.target_name)):
		frappe.throw(_("This reference cannot be made"), frappe.PermissionError)


def build(ctx: ViewCtx, rows: list) -> dict:
	"""{message: [item]} for the page's System messages. Rows are the viewer's own messages of ``ctx.thread``, so the
	message side of the rule is that thread's project and audience and the row's staff_only."""
	system = {r.name: r for r in rows if r.get("kind") == "System"}
	if not system:
		return {}
	pointers = frappe.get_all("Discuss Pointer", filters={"message": ["in", list(system)]},
		fields=["message", "target_type", "target_name"], order_by="creation asc, name asc")
	ctx.memo[POINTERS] = pointers
	targets, cards = _targets(ctx, pointers), _event_cards(ctx, pointers, rows)
	out, events = {}, set()
	for p in pointers:
		if p.target_type in EVENTS:
			events.add(p.message)
			card = cards.get((p.target_type, p.target_name))
			if card:
				out.setdefault(p.message, []).append(event_item(p.target_type, card))
			continue
		target, kind = targets.get((p.target_type, p.target_name)), by_type().get(p.target_type)
		message = frappe._dict(project=ctx.thread.project, audience=ctx.thread.audience,
			staff_only=system[p.message].get("staff_only"))
		if kind and kind.readers_read(message, target):
			out.setdefault(p.message, []).append(kind.item(ctx, target))
	ctx.memo.setdefault(HIDDEN, set()).update(events - set(out))
	return out


def _event_cards(ctx: ViewCtx, pointers, rows: list) -> dict:
	"""{(type, name): card} of the event records this viewer reads now, in the one resolver query the page's tags also
	use (the refs part then asks nothing more)."""
	from construction_core.discuss.parts.refs import page_refs
	from construction_core.records import resolve

	pairs = [(p.target_type, p.target_name) for p in pointers if p.target_type in EVENTS]
	if not pairs:
		return {}
	tags = [(x.ref_doctype, x.ref_name) for x in page_refs(ctx, rows)]
	return resolve.cards(ctx, pairs + tags)


def _targets(ctx: ViewCtx, pointers) -> dict:
	"""{(type, name): row} of the targets the viewer reads: one read as the viewer per registered type the page points
	at, which also answers respond()'s ``_ref`` check; an unregistered type is never read."""
	wanted = {}
	for p in pointers:
		wanted.setdefault(p.target_type, []).append(p.target_name)
	found = {}
	for kind in TARGETS:
		if wanted.get(kind.doctype):
			rows = [frappe._dict(r, doctype=kind.doctype) for r in ctx.readable(kind.doctype, wanted[kind.doctype],
				kind.fields)]
			if kind.prepare:
				kind.prepare(ctx, rows)
			found.update({(kind.doctype, r.name): r for r in rows})
	return found


PART = Part(key="pointer", audiences=frozenset({"Internal", "Client"}), senders=frozenset(), implies_kind=None,
	claim=None, build=build, capable=None)
