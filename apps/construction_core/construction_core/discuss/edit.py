"""Edit and remove a chat message (design §3.8, D-368, D-369, D-388): the record is kept, and only the latest text is
read by anyone but a System Manager.

**Edit** (the author, for 15 minutes, discuss.actions.can). The new text goes through the same checks as a send: its
length, the old ``@email`` mentions, and the mentions and refs parts' claims and tokens (P3-66), so an edit cannot
smuggle in a mention or a tag the send would refuse. Only those two parts may come with an edit: attachments, voice and
polls are never swapped. The text, mentions and tags it replaces go to a Discuss Message Version row (staff read); then
``content``, ``mentions`` and ``edited`` are set with db_set (D-388) and the message's tags are written again. People it
newly mentions get the mention's notice and follow, as at a send.

**Remove** (the author for 15 minutes, the project's manager at any time). The text and mentions, every version row
and every tag row move to Discuss Removed Text (System Managers only) and are deleted from their own doctypes; then
``content`` and ``mentions`` are emptied and ``removed`` set with db_set. Every file the chat made for the message (an
upload, a "Share and send" copy, a poll's picture, a voice note) is unshared and moved to the bin as the server, and every
attachment row of the message, links to staff originals included, stops drawing a card and a preview. Its poll closes,
its file request is cancelled (held uploads deleted for real, P3-71), its Agreed mark and pin go, and its room mirror
shows as removed too (§14.2: a mirror follows its reply).

Both are chat actions (discuss.actions): the parent message as the viewer, the portal checks for a client, never a
removed message or a card. ``history`` gives staff the earlier texts of an edited message.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from construction_core.core.events import emit
from construction_core.discuss import checks, rows, send
from construction_core.discuss.actions import can, changed, chat_action, drawn_by
from construction_core.permissions import switches_once

EDIT_PARTS = frozenset({"mentions", "refs"})
MAX_EDITS = 20  # per message (audit S3): the record stays readable and an edit cannot be used to flood
MADE = ("Upload", "Copy")  # files the chat made (discuss.media.chat_made); a Link is a staff original


@frappe.whitelist(methods=["POST"])
@chat_action("edit")
def edit(message: str, text: str | None = None, parts=None, *, _ctx=None, _row=None) -> None:
	"""Replace the text (and its mention and tag parts) of the caller's own message."""
	if "edit" not in can(_ctx, _row):
		frappe.throw(_("This message can no longer be edited"), frappe.PermissionError)
	claimed = send.parse_parts(parts)
	if set(claimed) - EDIT_PARTS:
		frappe.throw(_("An edit changes the words only"), frappe.PermissionError)
	if frappe.db.count("Discuss Message Version", {"message": _row.name}) >= MAX_EDITS:
		frappe.throw(_("This message has been edited {0} times: post a new message instead").format(MAX_EDITS))
	doc = frappe.get_doc("Discuss Message", _row.name)
	before = frappe._dict(content=doc.content, mentions=doc.mentions, refs=_refs(doc.name), creation=doc.creation)
	_check_text(doc, text, claimed)
	_keep_version(doc, before, _ctx.user)
	frappe.db.delete("Discuss Ref", {"message": doc.name})  # written again from the new text's tokens
	from construction_core.discuss.parts import refs

	refs.write(doc, (doc.flags.cc_parts or {}).get("refs") or [])
	doc.db_set({"content": doc.content, "mentions": doc.mentions, "edited": 1}, update_modified=False)
	_tell_new_mentions(doc)
	changed(_row, "edit")


@frappe.whitelist(methods=["POST"])
@chat_action("removed")
def remove(message: str, *, _ctx=None, _row=None) -> None:
	"""Remove a message: its words go to the System Managers' store, its files to the bin."""
	if "remove" not in can(_ctx, _row):
		frappe.throw(_("You cannot remove this message"), frappe.PermissionError)
	doc = frappe.get_doc("Discuss Message", _row.name)
	mentioned = [u for u in dict.fromkeys((doc.mentions or "").split("\n")) if u]
	_store_removed(doc, _ctx.user)
	_bin_files(doc.name, doc.file)
	frappe.db.set_value("Discuss Poll", {"message": doc.name, "closed_on": ["is", "not set"]},
		{"closed_on": now_datetime(), "closed_by": _ctx.user}, update_modified=False)
	from construction_core.discuss.parts import file_requests  # here: send imports the parts

	file_requests.cancel_for(doc.name)  # its held uploads are no chat file of the message: nothing else deletes them
	empty = {"content": "", "mentions": "", "removed": 1, "agreed": 0, "agreed_by": None, "agreed_on": None,
		"pinned": 0, "pinned_by": None, "pinned_on": None, "file": None, "reactions": None}  # file, reactions: C1
	doc.db_set(empty, update_modified=False)
	_unfollow_mentions(doc, mentioned)
	for card in drawn_by(doc.name):
		if _is_mirror(card, doc):
			frappe.db.set_value("Discuss Message", card.name, {"removed": 1, "pinned": 0, "agreed": 0},
				update_modified=False)
			send.queue_counters(card.thread, card.name)
	if not doc.staff_only:
		send.queue_counters(doc.thread, doc.name)
	changed(_row, "removed")


@frappe.whitelist(methods=["GET"])
def history(message: str) -> dict:
	"""Staff: the earlier texts of a message they read, oldest first, and when each was replaced. One refusal for
	missing, unreadable, removed and a client."""
	from construction_core.discuss import read
	from construction_core.discuss import view as chat_view

	viewer = frappe.session.user
	with switches_once():
		found = frappe.get_list("Discuss Message", filters={"name": message}, fields=["name", "thread", "removed"],
			limit=1, user=viewer) if isinstance(message, str) and message else None
		if not found or found[0].removed or not read.context(viewer, read.thread_for(viewer, found[0].thread)).staff:
			raise frappe.DoesNotExistError(_("Not found"))
		versions = frappe.get_all("Discuss Message Version", filters={"message": found[0].name},
			fields=["content", "written_on", "edited_by", "edited_on"], order_by="edited_on asc, creation asc")
	return chat_view.strip({"message": found[0].name, "versions": [{"text": chat_view.plain(v.content),
		"written_on": str(v.written_on) if v.written_on else None, "edited_on": str(v.edited_on),
		"edited_by": chat_view.person(v.edited_by)} for v in versions]})


# --- edit -----------------------------------------------------------------------------------------------------------


def _check_text(doc, text, claimed: dict) -> None:
	"""The send's checks on the new text, in the insert's order (DiscussMessage.before_insert): length and the old
	mentions (checks), the parts' claims, then the tokens. A message of files, voice or a poll may have no caption."""
	from construction_core.construction_core.doctype.discuss_message.discuss_message import settle_tokens

	doc.content = checks.text(text, empty=doc.kind not in (None, "", "Text"))
	doc.mentions = "\n".join(checks._mentions(doc))
	thread = frappe.get_doc("Discuss Thread", doc.thread)
	send.claim_parts(doc, thread, frappe._dict(parts=claimed))  # the kind it answers is the message's own: not used
	settle_tokens(doc)


def _keep_version(doc, before, user: str) -> None:
	last = frappe.get_all("Discuss Message Version", filters={"message": doc.name}, fields=["edited_on"],
		order_by="edited_on desc", limit=1)
	rows.insert("Discuss Message Version", {"content": before.content, "mentions": before.mentions,
		"refs": json.dumps(before.refs), "written_on": last[0].edited_on if last else before.creation,
		"edited_by": user, "edited_on": now_datetime()}, thread=doc.thread, message=doc.name)


def _refs(message: str) -> list:
	return [list(r) for r in frappe.get_all("Discuss Ref", filters={"message": message},
		fields=["position", "ref_doctype", "ref_name"], order_by="position asc", as_list=True)]


def _tell_new_mentions(doc) -> None:
	"""People an edit newly mentions: the notice, the mail link and the follow a send gives them. Anyone any earlier
	text of the message mentioned was told already (audit S3: editing a mention out and in again tells no one twice)."""
	from construction_core.discuss import rooms
	from construction_core.notifications import MENTION, mail_client_mention, notify
	from construction_core.permissions import is_client

	had = {u for v in frappe.get_all("Discuss Message Version", filters={"message": doc.name}, pluck="mentions")
		for u in (v or "").split("\n")}
	new = [u for u in dict.fromkeys((doc.mentions or "").split("\n")) if u and u not in had and u != doc.author]
	if not new:
		return
	thread = frappe.get_doc("Discuss Thread", doc.thread)
	notify([u for u in new if not is_client(u)], MENTION, thread, actor=doc.author, source=doc)
	for client in (u for u in new if is_client(u)):
		mail_client_mention(client, doc, thread)
	rooms.follow_message(frappe._dict(doc.as_dict(), mentions="\n".join(new), creation=now_datetime()))


# --- remove ---------------------------------------------------------------------------------------------------------


def _store_removed(doc, user: str) -> None:
	versions = frappe.get_all("Discuss Message Version", filters={"message": doc.name},
		fields=["content", "mentions", "refs", "written_on", "edited_by", "edited_on"], order_by="edited_on asc")
	rows.insert("Discuss Removed Text", {"content": doc.content, "mentions": doc.mentions,
		"versions": json.dumps([{k: str(v) if v is not None else None for k, v in x.items()} for x in versions]),
		"refs": json.dumps(_refs(doc.name)), "removed_by": user, "removed_on": now_datetime()}, thread=doc.thread,
		message=doc.name)
	# db.delete: the server's own removal, with no Deleted Document copy of the words (ChatRow)
	frappe.db.delete("Discuss Message Version", {"message": doc.name})
	frappe.db.delete("Discuss Ref", {"message": doc.name})


def _bin_files(message: str, legacy: str | None) -> None:
	"""Every File the chat made for the message: unshared and in the bin, as the server (the author may be a client,
	who has no write on a File). Each attachment row stops drawing its card and preview. The legacy single ``file`` is
	binned only when the chat made it (a project file it linked stays, audit C1)."""
	from construction_core.discuss import media

	attached = frappe.get_all("Discuss Attachment", filters={"message": message}, fields=["name", "file", "source"])
	made = {a.file for a in attached if a.source in MADE and a.file}
	if legacy and media.chat_made(legacy):
		made.add(legacy)
	for f in made:
		if frappe.db.exists("File", f):
			frappe.db.set_value("File", f, {"cc_trashed": 1, "cc_client_visible": 0}, update_modified=False)
			emit("storage.file_trashed", frappe.get_doc("File", f))  # the previews purge (P3-75)
	for a in attached:
		frappe.db.set_value("Discuss Attachment", a.name, "state", "Removed", update_modified=False)


def _unfollow_mentions(doc, mentioned: list) -> None:
	"""Audit M1: a follow keeps a mention time only from a message that is still there. For each person the removed
	message mentioned: the newest remaining mention of them by someone else in the thread; with none left, the next
	reason the follow still holds (a thread in a room: its root's author, a writer, an opener; a room is followed by
	mention only, §14.5), else the follow goes. As the server: no one else reads a follow."""
	if not mentioned:
		return
	in_room = frappe.db.get_value("Discuss Thread", doc.thread, "in_room")
	left = frappe.get_all("Discuss Message", filters={"thread": doc.thread, "removed": 0, "mentions": ["is", "set"]},
		fields=["author", "creation", "mentions"])
	for user in mentioned:
		row = frappe.db.get_value("Discuss Follow", {"thread": doc.thread, "user": user}, ["name", "reason"],
			as_dict=True)
		if not row:
			continue
		times = [m.creation for m in left if m.author != user and user in (m.mentions or "").split("\n")]
		reason = row.reason
		if reason == "mention" and not times:
			reason = _other_reason(doc.thread, user) if in_room else None
		if not reason:
			frappe.db.delete("Discuss Follow", {"name": row.name})
			continue
		frappe.db.set_value("Discuss Follow", row.name, {"reason": reason,
			"mentioned_on": max(times) if times else None}, update_modified=False)


def _other_reason(thread: str, user: str) -> str | None:
	from construction_core.discuss.rooms import REASONS

	root = frappe.db.get_value("Discuss Anchor", {"thread_id": thread}, "message_id")
	held = {
		"root": bool(root) and frappe.db.get_value("Discuss Message", root, "author") == user,
		"author": bool(frappe.db.exists("Discuss Message", {"thread": thread, "author": user, "removed": 0,
			"kind": ["!=", "System"]})),
		"opened": bool(frappe.db.exists("Discuss Read State", {"thread": thread, "user": user})),
	}
	return next((r for r in REASONS if held.get(r)), None)


def _is_mirror(card, message) -> bool:
	"""A mirror sits in the room of the reply's thread; a Team root card about a client message sits elsewhere and
	stays, drawing the message as removed."""
	room = frappe.db.get_value("Discuss Thread", message.thread, "in_room")
	return bool(room) and card.thread == room
