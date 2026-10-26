"""The approval part (approvals design §3.12, §3.14, §7; P3-78): the approval card, drawn per viewer at read time.

A System message in the Client room (the live card) or the Team room (the line when a client answers) carries one
Discuss Pointer to an Approval Request (approvals.card posts it). The pointer part reads the page's pointer rows once
and leaves them in ``ctx.memo``; this part, listed after it, draws the ones that target a request, so the page costs one
read of the requests as the viewer (``ViewCtx.readable``: the request's own list rule, which a test holds equal to
has_permission) and one of the chain, whatever the number of cards.

- **No claim, no sender**: only the server posts a card. A mention in text is a ``refs`` tag (records.resolve).
- **A viewer who may not read the request** gets no item, and the card is left out of their page (HIDDEN, as the design
  event cards are) instead of showing an empty System message (T30). The item carries ``_ref``, so respond() checks it again.
- **A mention never approves**: the item carries state and words only; the approval sheet is the one place to answer.
"""

import frappe

from construction_core.discuss.parts.pointer import APPROVAL, HIDDEN, POINTERS
from construction_core.discuss.registry import Part, ViewCtx

FIELDS = ("name", "project", "status", "decider_party", "subject_doctype", "subject_name", "subject_title", "due_date",
	"successor")


def build(ctx: ViewCtx, rows_: list) -> dict:
	"""{message: card} for the page's approval pointers this viewer may read."""
	from construction_core.approvals import card

	rows = {r.name: r for r in rows_}
	# this page's: the memo may still hold the pointer rows of an earlier page drawn with the same context
	pointers = [p for p in ctx.memo.get(POINTERS) or () if p.target_type == APPROVAL and p.message in rows]
	if not pointers or not ctx.thread.get("name"):
		return {}
	try:
		found = {r.name: r for r in ctx.readable(APPROVAL, [p.target_name for p in pointers], FIELDS)}
	except frappe.PermissionError:  # no role of the viewer reads requests (a partner, until P3-32)
		frappe.clear_last_message()
		found = {}
	known = card.chain(list(found))
	out = {}
	for p in pointers:
		target = found.get(p.target_name)  # read as this viewer: the storing rule held for the room's readers then, not now
		if target:
			out[p.message] = card.item(target, known[target.name], ctx.thread.audience, rows[p.message].get("creation"))
	ctx.memo.setdefault(HIDDEN, set()).update({p.message for p in pointers} - set(out))
	return out


PART = Part(key="approval", audiences=frozenset({"Internal", "Client"}), senders=frozenset(), implies_kind=None,
	claim=None, build=build, capable=None)
