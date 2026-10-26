"""The refs part (design §3.5, §6, §14.1; P3-66): tag files and records with #, their cards, and "Discuss this".

**The send.** The composer sends ``parts: {"refs": [{"doctype": ..., "name": ...}, ...]}`` (a file by its address:
``{"doctype": "File", "url": ...}``, never an id) and writes ``#[r:n]`` in the text, n counting from 1 in that list.
``claim`` checks each item as the sender (no writes):
- the type is on the allow-list for the room's audience (records.resolve.RECORD_TYPES; partners: P3-32);
- the item is of the same project and the sender reads it (an earlier version or a file in the bin is no item);
- in a Client room, every reader of the message may read it now (records.resolve.audience_reads, §14.4 row 2).
A missing item and one the sender cannot read get one error. Only staff are told "This item is not shared with the
client" (SEC-12). ``settle`` (DiscussMessage.before_insert) keeps the items the text's tokens name; a token with no item
refuses the send. ``write`` makes one Discuss Ref row per token, after the insert, under the same claim.

**The cards** (``build``): the page's refs in one query, then records.resolve.cards in one more, whatever the number of
messages or the mix of types (the inbox's last line draws none). A record the viewer cannot read now, one deleted and
one never shared give no item: the screen draws the token as the neutral "not available" chip (rule 2).

**The picker** (``picker``, D-391) has its own endpoint; global search keeps D-243's contract. ``q`` empty is the recent
mode (the newest items), one character matches the start of a title, more match anywhere in it or the record's number.
It offers only what the caller may read and, in a Client room, what the room's clients may read now. ``mode`` is the
caller's view (Simple by default: files and Canvas boards only); it only narrows.

**Discuss this** (D-413, D-418, R-32): ``discuss_rooms`` says which rooms staff may start or open a record's thread in
(the Team room always; the Client room only when the client may read the record, and never for a file: FILE_TEAM_ONLY),
and ``discuss_this`` opens the
record's one open thread in that room, or makes it with its root card, under a lock on the record (two first clicks
make one thread). Staff only; a record the caller cannot read answers "Not found", like a missing one.
"""

import re

import frappe
from frappe import _

from construction_core.discuss import read, rows
from construction_core.discuss import view as chat_view
from construction_core.discuss.parts.pointer import every_reader_reads
from construction_core.discuss.registry import Part, SendCtx, ViewCtx
from construction_core.permissions import (
	CLIENT_HIDDEN_STATE,
	client_may_see,
	client_portal_open,
	client_section_open,
	is_client,
	project_of,
	switches_once,
)
from construction_core.records import resolve

MAX = 10  # items a message tags
TOKEN = re.compile(r"#\[r:(\d{1,4})\]")
MARK = "#[r:"  # a page whose messages carry none reads no refs
PER_TYPE, MAX_QUERY = 6, 80
NOT_TAGGABLE = "This item cannot be tagged here"
NOT_SHARED = "This item is not shared with the client"
ROOMS = ("Internal", "Client")
CLIENT_COLUMNS = {"Approval Request": ["decider_party"]}  # what client_may_see reads, where it is not client_visible
# Audit S3 (provisional, for the lead's decision): a thread stores its anchor in Discuss Thread.anchor_name, a
# permlevel-0 field clients read by Frappe's routes (D-397, D-418), so a Client-room thread on a file would hand its
# client the File id (SEC-4). Until the anchor fields leave the client's reads, a file is discussed in the Team room.
FILE_TEAM_ONLY = "A file is discussed in the Team room"


# --- the send -------------------------------------------------------------------------------------------------------


def claim(ctx: SendCtx, value) -> list:
	"""[(doctype, name)] of the items, each checked as the sender."""
	if not isinstance(value, list) or len(value) > MAX or not all(isinstance(v, dict) for v in value):
		frappe.throw(_("The tags in this message are not valid"))
	audience = "Internal" if ctx.staff_only else ctx.thread.audience  # a legacy note's readers are the team
	with switches_once():
		# The project's switches, read before any item and whatever it names, so that no item's answer costs a read
		# another's does not (audit S1): a client's first switch reads them all at once.
		client_portal_open(ctx.thread.project)
		return [_item(ctx, audience, v) for v in value]


def _item(ctx: SendCtx, audience: str, value: dict) -> tuple:
	"""One item, read as the sender on one path whatever it names: a missing item, one of another project and one the
	sender cannot read cost the same reads and get the same answer (audit S1). Only an item the sender reads is then
	checked against what the room's readers may read."""
	doctype = value.get("doctype")
	t = resolve.by_doctype().get(doctype) if isinstance(doctype, str) else None
	if not t or audience not in t.audiences:
		_refuse()  # the allow-list: no read at all, for any item
	sender = ViewCtx(user=ctx.author, thread=ctx.thread, staff=ctx.sender == "staff")
	if t.doctype == "File":
		name = _file_by_url(sender, ctx.thread.project, value.get("url"))
	else:
		key = value.get("name")
		key = key if isinstance(key, str) else ""
		name = key if resolve.cards(sender, [(t.doctype, key or "-")], project=ctx.thread.project) else None
	if not name:
		_refuse()
	if not resolve.audience_reads(audience, frappe.get_doc(t.doctype, name)):
		if ctx.sender == "staff":
			frappe.throw(_(NOT_SHARED))
		_refuse()
	return (t.doctype, name)


def _record(doctype: str, name):
	if not (isinstance(name, str) and name and frappe.db.exists(doctype, name)):
		return None
	return frappe.get_doc(doctype, name)


def _file_by_url(sender: ViewCtx, project: str, url) -> str | None:
	"""The project's current file at that address that the sender reads: one read of the candidates, then the
	download rule for each in memory (attachments.readable_files), whatever the address names. One address can name
	several rows (Frappe keeps identical bytes once); a shared one first, so the conversation's clients may read it."""
	from construction_core.discuss.parts.attachments import readable_files

	url = url if isinstance(url, str) and url.startswith("/") else ""
	rows = frappe.get_all("File", filters={"file_url": url, "cc_project": project, "is_folder": 0, "cc_trashed": 0,
		"cc_version_of": ["is", "not set"]}, fields=["name", "file_name", *resolve.FILE_COLUMNS],
		order_by="cc_client_visible desc, creation asc", limit=20)
	readable, _revs = readable_files(sender, [r.name for r in rows], rows=rows)
	return next((r.name for r in rows if r.name in readable), None)


def _refuse():
	frappe.throw(_(NOT_TAGGABLE))


def settle(doc) -> None:
	"""DiscussMessage.before_insert, after the claims: [(position, doctype, name)] for the tokens the text carries. A
	token with no item is refused; an item no token names is not stored."""
	parts = doc.flags.get("cc_parts") or {}
	items = parts.get("refs") or []
	used = sorted({int(n) for n in TOKEN.findall(doc.content or "")})
	if any(not 1 <= n <= len(items) for n in used):
		frappe.throw(_("This message cannot be sent as written"))
	if "refs" in parts:
		parts["refs"] = [(n, *items[n - 1]) for n in used]


def write(doc, value: list) -> None:
	for position, doctype, name in value:
		rows.insert("Discuss Ref", {"ref_doctype": doctype, "ref_name": name, "position": position}, thread=doc.thread,
			message=doc.name)


def check_row(row) -> None:
	"""DiscussRef's insert: a registered type for the message's audience, the same project, and every reader of the
	message reads the record (the claim checked it as the sender; this holds it for any later server path)."""
	t = resolve.by_doctype().get(row.ref_doctype)
	audience = "Internal" if row.staff_only else row.audience
	doc = _record(row.ref_doctype, row.ref_name) if t else None
	if not (t and doc and audience in t.audiences and every_reader_reads(row, frappe._dict(doc.as_dict(),
			project=project_of(doc))) and resolve.audience_reads(audience, doc)):
		frappe.throw(_(NOT_TAGGABLE), frappe.PermissionError)


# --- the cards ------------------------------------------------------------------------------------------------------


def build(ctx: ViewCtx, rows_: list) -> dict:
	"""{message: [card]} for the refs ``ctx.user`` may read, each with its ``pos`` in the text."""
	refs = page_refs(ctx, rows_)
	if not refs:
		return {}
	cards = resolve.cards(ctx, [(x.ref_doctype, x.ref_name) for x in refs])
	out = {}
	for x in refs:
		card = cards.get((x.ref_doctype, x.ref_name))
		if card:
			out.setdefault(x.message, []).append({**card, "pos": x.position})
	return out


def page_refs(ctx: ViewCtx, rows_: list) -> list:
	"""The page's Discuss Ref rows, read once per page: the pointer part asks first when the page has design event
	cards, so their records and the tags share one resolver query (P3-69)."""
	if not ctx.thread.get("name"):
		return []
	tagged = tuple(r.name for r in rows_ if MARK in (r.get("content") or ""))
	if not tagged:
		return []
	key = ("cc_page_refs", tagged)
	if key not in ctx.memo:
		ctx.memo[key] = frappe.get_all("Discuss Ref", filters={"message": ["in", list(tagged)]},
			fields=["message", "ref_doctype", "ref_name", "position"], order_by="position asc")
	return ctx.memo[key]


def capable(ctx: ViewCtx, thread) -> bool:
	return thread.status != "Locked" and thread.audience in PART.audiences


# --- the picker -----------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def picker(thread: str, q: str | None = None, mode: str | None = None) -> dict:
	"""What the caller may tag in ``thread`` (D-391): per type, the newest PER_TYPE matches."""
	viewer = frappe.session.user
	with switches_once():
		t = read.thread_for(viewer, thread)
		ctx = read.context(viewer, t)
		q = (q if isinstance(q, str) else "").strip()[:MAX_QUERY]
		items = []
		if t.status != "Locked":
			for rt in resolve.allowed(t.audience, mode):
				if t.audience == "Client" and not client_section_open(rt.doctype, t.project):
					continue  # the room's clients cannot read this section now
				items += _files(ctx, t, q) if rt.doctype == "File" else _records(ctx, t, rt, q)
	return chat_view.strip({"items": items})


def _like(text: str) -> str:
	return re.sub(r"([\\%_])", r"\\\1", text)


def _records(ctx: ViewCtx, t, rt, q: str) -> list:
	filters = {"project": t.project}
	if t.audience == "Client":
		filters.update(_client_filters(rt.doctype))
	or_filters = None
	if len(q) == 1:
		filters[rt.title] = ["like", f"{_like(q)}%"]
	elif q:
		or_filters = {rt.title: ["like", f"%{_like(q)}%"], "name": ["like", f"%{_like(q)}%"]}
	fields = ["name", f"{rt.title} as title", *([f"{rt.state} as state"] if rt.state else []),
		*([f"{rt.reference} as number"] if rt.reference else []),
		*(CLIENT_COLUMNS.get(rt.doctype, ["client_visible"]) if t.audience == "Client" else [])]
	try:
		found = frappe.get_list(rt.doctype, filters=filters, or_filters=or_filters, fields=fields,
			order_by="modified desc", limit=PER_TYPE, user=ctx.user)
	except frappe.PermissionError:
		frappe.clear_last_message()
		return []
	out = []
	for r in found:
		if t.audience == "Client" and not client_may_see(frappe._dict(r, doctype=rt.doctype,
				**({rt.state: r.get("state")} if rt.state else {}))):
			continue
		card = resolve.record_card(rt, frappe._dict(r, state=r.get("state")))
		out.append({k: v for k, v in card.items() if k != "_ref"})
	return out


def _client_filters(doctype: str) -> dict:
	"""What the room's clients may read now, as list filters (permissions.CLIENT_ONLY_SQL's rules)."""
	if doctype == "Approval Request":  # P3-78: not a Draft, decided by a client (approvals.read); P3-82: not In internal
		return {"decider_party": "client", "status": ["not in", ["Draft", "In internal review"]]}  # review either
	if doctype == "Project Document":
		return {"client_visible": 1, "status": "Published"}
	if doctype in CLIENT_HIDDEN_STATE:
		field, hidden = CLIENT_HIDDEN_STATE[doctype]
		return {"client_visible": 1, field: ["!=", hidden]}
	return {"client_visible": 1}


def _files(ctx: ViewCtx, t, q: str) -> list:
	"""The project's current files: candidates by a server read, then the download rule for each as the caller
	(attachments.readable_files: Frappe's File list would show a non-System user only their own files)."""
	from construction_core.discuss.parts.attachments import readable_files

	filters = {"cc_project": t.project, "is_folder": 0, "cc_trashed": 0, "cc_version_of": ["is", "not set"]}
	if t.audience == "Client":
		filters["cc_client_visible"] = 1
	if q:
		filters["file_name"] = ["like", f"{_like(q)}%" if len(q) == 1 else f"%{_like(q)}%"]
	found = frappe.get_all("File", filters=filters, fields=["name", "file_name", *resolve.FILE_COLUMNS],
		order_by="modified desc", limit=PER_TYPE * 3)
	readable, _revs = readable_files(ctx, [f.name for f in found], rows=found)
	out, urls = [], set()
	for f in found:
		if f.name in readable and f.file_url not in urls and len(out) < PER_TYPE:
			urls.add(f.file_url)  # one address, one item: the send finds the readable row again
			out.append({k: v for k, v in resolve.file_card(f).items() if k != "_ref"})
	return out


# --- Discuss this ---------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def discuss_rooms(doctype: str, name: str) -> dict:
	"""The rooms staff may discuss a record in, with its open thread in each (None: "Discuss this" makes one)."""
	from construction_core.discuss import rooms

	doc = _discussable(doctype, name)
	return {"rooms": [{"room": room, "thread": rooms.open_thread(doc.doctype, doc.name, room)}
		for room in ROOMS if room == "Internal" or _client_room(doc)]}


@frappe.whitelist(methods=["POST"])
def discuss_this(doctype: str, name: str, room: str = "Internal") -> dict:
	"""The record's open thread in ``room`` (the Team room by default), made on first use with its root card there. The
	Client room only when the project's clients may read the record now."""
	from construction_core.discuss import rooms
	from construction_core.discuss.api import lost_race_once
	from construction_core.discuss.provider import DiscussChat

	doc = _discussable(doctype, name)
	if room not in ROOMS:
		frappe.throw(_("Choose the Team room or the Client room"))
	if room == "Client" and doc.doctype == "File":
		frappe.throw(_(FILE_TEAM_ONLY))
	if room == "Client" and not _client_room(doc):
		frappe.throw(_(NOT_SHARED))

	def open_():
		frappe.db.get_value(doc.doctype, doc.name, "name", for_update=True)  # one thread for two first clicks
		return DiscussChat().ensure_thread(doc.doctype, doc.name, room)  # a file's thread is "File" (provider.label)

	thread = lost_race_once(open_)
	return {"thread": thread, "room": rooms.room(project_of(doc), room)}


def _discussable(doctype, name):
	"""A record of a taggable type that the staff caller reads; anything else is "Not found"."""
	if is_client(frappe.session.user):
		frappe.throw(_("This is for the project team only"), frappe.PermissionError)
	t = resolve.by_doctype().get(doctype) if isinstance(doctype, str) else None
	doc = _record(doctype, name) if t and doctype != "Approval Request" else None  # an approval has its own card (P3-78)
	if not doc or not project_of(doc) or not frappe.has_permission(doctype, "read", doc=doc, throw=False) or (
			doctype == "File" and (doc.is_folder or doc.cc_trashed or doc.cc_version_of)):
		frappe.clear_last_message()
		raise frappe.DoesNotExistError(_("Not found"))
	return doc


def _client_room(doc) -> bool:
	"""The project's clients may read ``doc`` and the conversation now: the portal, the record's section and the
	Discussion section are on (§14.1)."""
	if doc.doctype == "File":
		return False  # FILE_TEAM_ONLY
	project = project_of(doc)
	return (resolve.by_doctype()[doc.doctype].audiences >= {"Client"} and resolve.audience_reads("Client", doc)
		and client_portal_open(project) and client_section_open("Discuss Message", project))


PART = Part(key="refs", audiences=frozenset({"Internal", "Client"}), senders=frozenset({"staff", "client"}),
	implies_kind=None, claim=claim, build=build, capable=capable, write=write)
