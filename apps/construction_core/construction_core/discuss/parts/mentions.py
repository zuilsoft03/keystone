"""The mentions part (design §3.4, §6; P3-66): who a sender may mention, the tokens a message stores, and the chips.

**The list** (``people``) is the conversation's audience, from the project's member rows, never a user search:
- a Team-room conversation (and a legacy staff-only note): the project's team only (SEC-11);
- a Client-room conversation: the team and the project's client contacts, while the portal and its Discussion section
  are on (D-105, D-117), as the realtime router reads them (live.readers);
- a partner room: the team and that firm's people, from P3-32 (D-444; ``audience`` answers nobody for it until then).
Disabled accounts are left out. A thread the caller may not read answers "Not found", like a missing one.

**The send.** The composer sends ``parts: {"mentions": [user, ...]}`` and writes ``@[u:n]`` in the text, n counting from
1 in that list. ``claim`` keeps each person the list would offer and leaves an empty slot for anyone else: no error, so
a send never tells the sender who is a member (F6). ``settle`` (DiscussMessage.before_insert) stores the slots in the
message's ``mentions`` field, positional, so ``@[u:n]`` is the n-th line; a slot no token names is emptied too, so
nobody is told of a mention the text does not show. A token with no slot refuses the send with one neutral error,
whoever it would name. Old ``@email`` text (checks.run, FIT-20) is kept after the slots. At most MAX people.

**The chips** (``build``): each non-empty slot as {pos, user, name, image}, read from the cache like the authors (no
query). Notices (notifications.on_message: a staff bell notice, a client's email link) and Discuss Follow rows with
``mentioned_on`` (rooms.follow_message, for the Mentions filter and the inbox's Mentions me) read the same field.
"""

import re

import frappe
from frappe import _

from construction_core.discuss import live, read
from construction_core.discuss import view as chat_view
from construction_core.discuss.registry import Part, SendCtx, ViewCtx
from construction_core.permissions import client_section_open, switches_once

MAX = 20  # people a message mentions (§3.4)
TOKEN = re.compile(r"@\[u:(\d{1,4})\]")
SHOWN = 50  # people the list answers


def audience(project: str, audience_: str, staff_only=False) -> list:
	"""The User rows (name, full_name, user_image, user_type) of the people a conversation of ``audience_`` offers."""
	users = live.staff_members(project)
	if audience_ == "Client" and not staff_only and client_section_open("Discuss Message", project):
		users += live.client_members(project)  # none while the portal is off
	elif audience_ not in ("Internal", "Client"):
		return []  # Partner: P3-32 (D-444)
	users = list(dict.fromkeys(u for u in users if u))
	if not users:
		return []
	return frappe.get_all("User", filters={"name": ["in", users], "enabled": 1},
		fields=["name", "full_name", "user_image", "user_type"], order_by="full_name asc")


# --- the send -------------------------------------------------------------------------------------------------------


def claim(ctx: SendCtx, value) -> list:
	"""The slots: each person the list offers, else "". Refuses only a list that is not one: its shape and length,
	never who is in it."""
	if not isinstance(value, list) or len(value) > MAX or not all(isinstance(v, str) for v in value):
		frappe.throw(_("The mentions in this message are not valid"))
	offered = {u.name for u in audience(ctx.thread.project, ctx.thread.audience, ctx.staff_only)}
	slots, seen = [], set()
	for v in value:
		slots.append(v if v in offered and v not in seen else "")
		seen.add(v)
	return slots


def settle(doc) -> None:
	"""DiscussMessage.before_insert, after the claims: the ``mentions`` field from the claimed slots and the tokens the
	text carries, then the old ``@email`` mentions checks.run found. A token with no slot is refused."""
	slots = (doc.flags.get("cc_parts") or {}).get("mentions") or []
	used = {int(n) for n in TOKEN.findall(doc.content or "")}
	if any(not 1 <= n <= len(slots) for n in used):
		frappe.throw(_("This message cannot be sent as written"))
	slots = [u if i + 1 in used else "" for i, u in enumerate(slots)]  # empty slots stay: positions never shift
	legacy = [u for u in (doc.mentions or "").split("\n") if u and u not in slots]
	kept = len([u for u in slots if u])
	doc.mentions = "\n".join([*slots, *legacy[:max(MAX - kept, 0)]])


# --- the chips ------------------------------------------------------------------------------------------------------


def build(ctx: ViewCtx, rows: list) -> dict:
	"""{message: [chip]}; no query (names from the cache). The inbox's last line (no thread name) draws none."""
	if not ctx.thread.get("name"):
		return {}
	out = {}
	for r in rows:
		chips = [{"pos": i + 1, **chat_view.person(u)} for i, u in enumerate((r.get("mentions") or "").split("\n")) if u]
		if chips:
			out[r.name] = chips
	return out


def capable(ctx: ViewCtx, thread) -> bool:
	return thread.status != "Locked" and thread.audience in PART.audiences


# --- the list -------------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def people(thread: str, q: str | None = None) -> dict:
	"""The people the caller may mention in ``thread``, matching ``q`` by name or address. Only the conversation's
	audience: whether anyone else is a member is never told, and an unknown thread answers like a forbidden one."""
	viewer = frappe.session.user
	with switches_once():
		t = read.thread_for(viewer, thread)
		if t.status == "Locked":
			return {"people": []}
		q = (q if isinstance(q, str) else "").strip().lower()[:80]
		rows = [u for u in audience(t.project, t.audience)
			if not q or q in (u.full_name or "").lower() or q in u.name.lower()]
	return chat_view.strip({"people": [{"user": u.name, "name": u.full_name or u.name, "image": u.user_image,
		"team": u.user_type != "Website User"} for u in rows[:SHOWN]]})


PART = Part(key="mentions", audiences=frozenset({"Internal", "Client"}), senders=frozenset({"staff", "client"}),
	implies_kind=None, claim=claim, build=build, capable=capable)
