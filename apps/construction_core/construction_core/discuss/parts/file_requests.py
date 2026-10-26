"""The file requests part (design §3.10, H-10; P3-71; D-379, D-380, D-384, D-389, D-158, D-182, D-420): the files the
team asks for, as a checklist card in a conversation.

**The send** (staff only): ``parts: {"file_requests": {"title", "due_on", "folder", "recipients", "items":
[{"description", "required", "example_file"}]}}``, on its own (no files, voice or poll in the same message), in an
open thread the sender writes in; the message needs its text, as any Text message. ``claim`` checks the shape (1 to 20
items) and the people: each recipient is in the conversation's audience now (a Client thread: the project's client
contacts who can open it; an Internal thread: the project's staff; partners join at P3-32). ``due_on`` defaults to 5
working days later. ``write`` makes the File Request with its items and recipients. ``from_project`` sends one from a
project, into the room rooms.route names (D-420).

**States.** An item goes Waiting -> Received (an upload is held) -> Accepted; ask_again sends a Received item back to
Waiting with a reason. A request is Open, Done once every required item is Accepted and no item is Received (a held
upload waits on review), checked after accept and after ask_again, or Cancelled by staff or with its removed card
(every held upload deleted). Nothing changes a request that is not Open.

**Uploads** run the attachments pipeline (check_burst, check_rate for clients, media.slot, media.checked, the large-file
scan, the client cap of D-182) and stage a Discuss Attachment that is then Held: no expiry, so no send claims it, the
purge leaves it and no card or gallery draws it (each of them reads Pending or Sent only). Its bytes wait in the
staging folder, which the backups do not hold. ``accept`` makes the File in the request's folder under the P3-07 claim
shape, the uploader's own (D-158: a client's file is theirs and the team's until shared); ``ask_again`` and ``cancel``
delete held uploads for real (D-389).

**The card** (``build``): the page's requests with their items, recipients and held uploads in one statement. Staff see
every item and review Received ones; a recipient sees the items and sends files; anyone else sees counts and states. A
held file shows only to staff and its uploader.

**Reminders** (D-379, D-380, D-384): email and the bell only, to each recipient while a required item is Waiting: the
day before the due date, on it, then every 2 days, at most 4 for staff and 2 for clients, Nudge included. The email
names no project and no item: a sign-in link only, in invitation words.
"""

import json
import mimetypes
import os
import time
from urllib.parse import quote, urlencode

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import add_days, cint, date_diff, get_url, getdate, now_datetime, nowdate
from werkzeug.wrappers import Response

from construction_core import client_files
from construction_core.discuss import actions, media, read, rooms, rows
from construction_core.discuss import view as chat_view
from construction_core.discuss.parts import attachments
from construction_core.discuss.registry import Part, SendCtx, ViewCtx, sender_of
from construction_core.notifications import FILES_ASKED_AGAIN, FILES_RECEIVED, FILES_REMINDER, notify
from construction_core.permissions import client_section_open, is_client, is_member, switches_once
from construction_core.providers.storage import IMAGE_TYPES, ROOT

KEY = "file_requests"
DOCTYPE, ITEM, RECIPIENT = "File Request", "File Request Item", "File Request Recipient"
OPEN, DONE, CANCELLED = "Open", "Done", "Cancelled"
WAITING, RECEIVED, ACCEPTED = "Waiting", "Received", "Accepted"
HELD = "Held"  # Discuss Attachment.state of an upload waiting on an item
KEYS = {"title", "due_on", "folder", "recipients", "items"}
ITEM_KEYS = {"description", "required", "example_file"}
MAX_ITEMS, MAX_TITLE, MAX_DESCRIPTION, MAX_REASON = 20, 140, 200, 300
DUE_WORKING_DAYS, MAX_DUE_DAYS = 5, 90  # D-379
CAPS = {"staff": 4, "client": 2}  # reminders per recipient and request, Nudge included (D-379, D-384)
EVERY = 2  # days between reminders after the due date
ALONE = ("attachments", "voice", "polls")  # parts that make the message another kind: a request goes on its own
SENDING = "cc_discuss_write"  # send.CLAIM: the whole send this part is claimed in
HELD_FIELDS = ["name", "uploader", "staged", "content_hash", "has_preview", "project", "file_size", "file_name", "ext",
	"checking", "scan_reason", "creation"]
# One statement for a page's requests: each item row with its request, its held upload and the request's recipients.
CARD_SQL = """select r.name, r.message, r.thread, r.project, r.audience, r.staff_only, r.title, r.due_on, r.status,
		r.folder, r.requested_by, i.name as item, i.description, i.required, i.status as item_status, i.uploaded_by,
		i.reason, i.example_file, i.file, a.name as held, a.file_name as held_name, a.file_size as held_size,
		a.kind as held_kind, a.checking as held_checking, a.scan_reason as held_reason,
		(select group_concat(x.user order by x.idx separator '\n') from `tabFile Request Recipient` x
			where x.parent = r.name and x.parenttype = 'File Request') as recipients
	from `tabFile Request` r
	join `tabFile Request Item` i on i.parent = r.name and i.parenttype = 'File Request'
	left join `tabDiscuss Attachment` a on a.name = i.attachment and a.state = 'Held'
	where r.{by} in %(names)s order by r.name, i.idx"""


# --- the send -------------------------------------------------------------------------------------------------------


def claim(ctx: SendCtx, value) -> dict:
	"""The request, checked and normalised; no writes."""
	if not isinstance(value, dict) or set(value) - KEYS:
		frappe.throw(_("The file request is not valid"))
	if ctx.staff_only:  # a legacy note's card would reach none of the people asked
		frappe.throw(_("A file request is shared with the conversation"), frappe.PermissionError)
	sending = frappe.flags.get(SENDING)
	if sending and set(sending.parts or {}) & set(ALONE):
		frappe.throw(_("Send a file request on its own"))
	title = _text(value.get("title"), MAX_TITLE)
	items = value.get("items")
	if not title or not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
		frappe.throw(_("A file request has a title and 1 to {0} files").format(MAX_ITEMS))
	client = ctx.thread.audience == "Client"
	out = []
	for i in items:
		item = _item(i, ITEM_KEYS)
		item["example_file"] = _example(ctx, i.get("example_file"), client)
		out.append(item)
	return {"title": title, "due_on": _due_on(value.get("due_on")), "folder": _folder(ctx.thread, value.get("folder")),
		"recipients": _recipients(ctx.thread, value.get("recipients")), "items": out}


def template_items(raw) -> list:
	"""A template's checklist (File Request Template.validate): 1 to 20 items, each a description and required."""
	try:
		value = json.loads(raw) if isinstance(raw, str) else raw
	except ValueError:
		value = None
	if not isinstance(value, list) or not 1 <= len(value) <= MAX_ITEMS:
		frappe.throw(_("A template has 1 to {0} files").format(MAX_ITEMS))
	return [_item(i, {"description", "required"}) for i in value]


def _item(value, keys) -> dict:
	if not isinstance(value, dict) or set(value) - keys:
		frappe.throw(_("The file request is not valid"))
	description = _text(value.get("description"), MAX_DESCRIPTION)
	if not description:
		frappe.throw(_("Each file needs a description"))
	return {"description": description, "required": 1 if cint(value.get("required", 1)) else 0}


def _text(value, limit: int) -> str:
	text = value.strip() if isinstance(value, str) else ""
	if len(text) > limit:
		frappe.throw(_("These words are at most {0} characters").format(limit))
	return text


def _due_on(value):
	"""5 working days on by default; a date given is never past and at most 90 days ahead (D-379)."""
	today_ = getdate(nowdate())  # the site's zone
	if value in (None, ""):
		return working_days_after(today_, DUE_WORKING_DAYS)
	try:
		due = getdate(value) if isinstance(value, str) else None
	except Exception:
		due = None
	if not due or due < today_ or due > add_days(today_, MAX_DUE_DAYS):
		frappe.throw(_("Choose a due date in the next {0} days").format(MAX_DUE_DAYS))
	return due


def working_days_after(start, days: int):
	"""``days`` working days after ``start``, Monday to Friday.
	shortcut: no holiday list (provisional, D-379), until the firm keeps one."""
	due = start
	while days:
		due = add_days(due, 1)
		if due.weekday() < 5:
			days -= 1
	return due


def _folder(thread, value) -> str | None:
	"""Where accepted files go. By default the clients' own inbox for a client request (P3-07), and for staff the
	internal conversation folder, made at write (None here: a claim writes nothing). A folder chosen is one of this
	project's tree (its staff read it, as the Files page does: the sender reads the thread), never the conversations'
	client folder (D-390), and the clients' inbox only for clients."""
	from construction_core.workspace import client_folders

	ours, client = client_folders(thread.project), thread.audience == "Client"
	if value in (None, ""):
		if client and not ours["inbox"]:
			frappe.throw(_("This project cannot receive files yet. Ask the project team."))
		return ours["inbox"] if client else None
	f = frappe.db.get_value("File", value, ["name", "is_folder", "cc_project", "cc_trashed"], as_dict=True) \
		if isinstance(value, str) else None
	if (not f or not f.is_folder or f.cc_project != thread.project or f.cc_trashed or f.name == ours["chat"]
			or (f.name == ours["inbox"] and not client) or not f.name.startswith(ROOT + "/")):
		frappe.throw(_("Choose a folder of this project"), frappe.PermissionError)
	return f.name


def _example(ctx: SendCtx, value, client: bool) -> str | None:
	"""An item's example: a current file of this project the sender reads (the attachments part's own check), and for a
	client request one the team already shares with the client: it is never shared here."""
	if value in (None, ""):
		return None
	f = attachments._linkable(value if isinstance(value, str) else None, ctx.thread.project, ctx.author,
		_("Choose an example from this project's files"))
	if client and not f.cc_client_visible:
		frappe.throw(_("Share the example with the client first"), frappe.PermissionError)
	return f.name


def _recipients(thread, value) -> list:
	if (not isinstance(value, list) or not value or not all(isinstance(u, str) and u for u in value)
			or len(set(value)) != len(value)):
		frappe.throw(_("Choose who to ask for the files"))
	if not all(may_ask(thread, u) for u in value):
		frappe.throw(_("Ask only people in this conversation"), frappe.PermissionError)
	return list(value)


def may_ask(thread, user: str) -> bool:
	"""Whether ``user`` may be asked in this thread now: an enabled person who can open it, a client contact in a Client
	thread and a member of the project's staff in an Internal one (a System Manager reads every thread, so reading is not
	enough; partners: P3-32). Asked again at every page, upload and reminder, so a request never reaches someone outside
	the project (threat row H-10). ``thread`` carries name, audience and project."""
	if not frappe.db.get_value("User", user, "enabled") or is_client(user) != (thread.audience == "Client"):
		return False
	if thread.audience != "Client" and not is_member(user, thread.project):
		return False
	return bool(frappe.has_permission("Discuss Thread", "read", doc=thread.name, user=user, throw=False))


def write(doc, value: dict) -> None:
	"""The request, its items and its recipients, under the send's claim, after the card's insert."""
	rows.insert(DOCTYPE, {"title": value["title"], "due_on": value["due_on"],
		"folder": value["folder"] or _internal_folder(doc.project), "requested_by": doc.author,
		"items": [{**i, "status": WAITING} for i in value["items"]],
		"recipients": [{"user": u, "reminders": 0} for u in value["recipients"]]}, thread=doc.thread, message=doc.name)


def _internal_folder(project: str) -> str:
	from construction_core.providers.storage import INTERNAL_CHAT, get_storage
	from construction_core.workspace import root_path

	return get_storage().ensure_path(f"{root_path(project)}/{INTERNAL_CHAT}", project)  # made on first use (FIT-13)


# --- the card -------------------------------------------------------------------------------------------------------


def build(ctx: ViewCtx, rows_: list) -> dict:
	"""{message: card} for the page's requests, in one statement whatever their number."""
	if not ctx.thread.get("name"):
		return {}  # the inbox's last line draws no card
	names = [r.name for r in rows_ if r.get("kind") == "Text"]  # a request goes alone, so its card is a Text message
	if not names:
		return {}
	return {r.message: card(ctx, r) for r in requests(names)}


def requests(names, by: str = "message", lock: bool = False) -> list:
	"""The requests of these messages (``by`` "name": these requests), each with ``items`` and ``recipients``."""
	got = {}
	sql = CARD_SQL.format(by="name" if by == "name" else "message") + (" for update" if lock else "")
	for x in frappe.db.sql(sql, {"names": tuple(names)}, as_dict=True):
		r = got.get(x.name)
		if r is None:
			r = got[x.name] = frappe._dict(x, items=[], recipients=[u for u in (x.recipients or "").split("\n") if u])
		r["items"].append(x)
	return list(got.values())


def card(ctx: ViewCtx, r) -> dict:
	"""The request as ``ctx.user`` sees it: staff every item, a recipient the items, anyone else counts and states."""
	open_ = r.status == OPEN and ctx.thread.get("status") != "Locked"
	asked = ctx.user in r.recipients  # staff asked in an Internal thread review others' files and send their own
	role = "staff" if ctx.staff else "recipient" if asked else "other"
	sends = asked and (ctx.staff or client_section_open("File", r.project))  # the upload's own Files switch (FIT-19)
	items = []
	for i in r["items"]:
		item = {"item": i.item, "required": bool(i.required), "status": i.item_status}
		if role != "other":
			item.update(description=i.description, reason=i.reason or None)
		if i.held and (ctx.staff or i.uploaded_by == ctx.user):  # a held file: staff and its uploader only
			item["held"] = {"file_name": i.held_name, "size": cint(i.held_size), "kind": i.held_kind,
				"checking": bool(i.held_checking), "refused": i.held_reason or None}
		if ctx.staff:
			review = open_ and i.item_status == RECEIVED and i.uploaded_by != ctx.user
			item.update(uploaded_by=chat_view.person(i.uploaded_by) if i.uploaded_by else None, can_ask_again=review,
				can_accept=bool(review and i.held and not i.held_checking and not i.held_reason))
		if asked:
			item.update(mine=i.uploaded_by == ctx.user, may_upload=sends and open_ and _fillable(i))
		items.append(item)
	out = {"request": r.name, "title": r.title, "due_on": str(r.due_on) if r.due_on else None, "status": r.status,
		"received": sum(i.item_status in (RECEIVED, ACCEPTED) for i in r["items"]), "total": len(r["items"]),
		"role": role, "asked": asked, "items": items, "may_upload": any(i.get("may_upload") for i in items)}
	if role == "staff":
		out.update(requested_by=chat_view.person(r.requested_by), recipients=[chat_view.person(u) for u in r.recipients],
			can_nudge=open_, can_cancel=open_ and (r.requested_by == ctx.user or actions.manages(ctx)))
	return out


def _fillable(i) -> bool:
	"""An item an upload may fill: Waiting, or Received with an upload its scan refused (the new one replaces it)."""
	return i.item_status == WAITING or bool(i.item_status == RECEIVED and i.held and i.held_reason)


def capable(ctx: ViewCtx, thread) -> bool:
	"""Staff ask for files in an open thread (§3.10)."""
	return ctx.staff and thread.status != "Locked" and thread.audience in PART.audiences


# --- the endpoints --------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def page(request: str) -> dict:
	"""The request as the caller may see it: the card's answer with each item's example and accepted file (when the
	caller reads them), whether they may upload now and, for a client asked, how many more files the project takes from
	its clients today (client_files.sent_today: the cap's own count). One "not found" for a request they may not see."""
	with switches_once():
		ctx, r = _seen(request)
		return _page(ctx, r)


@frappe.whitelist(methods=["POST"])
def from_project(project: str, title: str, recipients, items, due_on: str | None = None, folder: str | None = None,
		client_id: str | None = None) -> dict:
	"""A request made from a project, not a conversation (D-420): rooms.route names the room, the Client room when
	everyone asked is a client, else the Team room; the card goes through the one send path, with the title as its
	text. Answers {thread, message, request}."""
	from construction_core.discuss.send import send_impl  # here: send imports the parts

	if sender_of(frappe.session.user) != "staff":
		frappe.throw(_("This is for the project team only"), frappe.PermissionError)
	if not (isinstance(project, str) and project
			and frappe.has_permission("Construction Project", "read", doc=project, throw=False)):
		raise frappe.DoesNotExistError(_("Not found"))
	people, items = _json(recipients), _json(items)
	client = isinstance(people, list) and bool(people) and all(isinstance(u, str) and is_client(u) for u in people)
	room = rooms.route(frappe.get_doc("Construction Project", project), client=client)
	spec = {"title": title, "recipients": people, "items": items, "due_on": due_on, "folder": folder}
	message = send_impl(room, title if isinstance(title, str) else "", client_id=client_id, parts_in={KEY: spec})
	return {"thread": room, "message": message, "request": frappe.db.get_value(DOCTYPE, {"message": message})}


@frappe.whitelist(methods=["POST"])
def upload(item: str, taken_on: str | None = None) -> dict:
	"""A person asked fills an item from this device, through the attachments pipeline; the staged row is then Held
	(no expiry) and the item Received. The requester gets one bell notice per request until they read it. Answers the
	request page."""
	started = time.monotonic()
	frappe.form_dict.pop("file_size", None)  # File.validate would take it over the real size
	user = frappe.session.user
	ctx, r, i = _item_of(item, acting=False)  # no row lock through the scan (up to 110 s); _hold_for locks and checks again
	actions.count(user)  # the rate limit every change has (_acting)
	t, sender = attachments._place(r.thread)  # the send's checks for the sender kind, and the Files switch (FIT-19)
	if user not in r.recipients or not may_ask(t, user):
		frappe.throw(_("Only the people asked can send these files"), frappe.PermissionError)
	if r.status != OPEN:
		frappe.throw(_("This file request is closed"))
	if not _fillable(i):
		frappe.throw(_("This file is not waited for"))
	client_files.check_burst(user, None if sender == "client" else client_files.STAFF_BURST)
	if sender == "client":
		from construction_core.discuss.send import check_rate  # here: send imports the parts

		check_rate(user)  # as a chat upload: a message the limit would refuse costs no scan
	with media.slot(user), attachments._room_types(sender, t):
		display, ext, content = attachments._one_file()
		taken = attachments._taken(taken_on)
		if len(content) > client_files.SCAN_IN_REQUEST:  # D-417: a large model file is scanned after the request
			with client_files.large_slot():
				content = attachments._checked_but_scan(ext, content, t.project, client=sender == "client")
				name = media.stage(t, user, display, ext, content, taken=taken)
				attachments._hold(name)
		else:
			content = media.checked(ext, content, t.project, started=started, client=sender == "client")
			name = media.stage(t, user, display, ext, content, taken=taken)
	_hold_for(r, i.item, name, user)
	return _page(ctx, _one(r.name))


@frappe.whitelist(methods=["GET"])
def held(item: str):
	"""The held bytes, for review only: staff who read the thread, and the uploader. Never while its scan runs or once
	it refused the file. One "not found" for everyone else."""
	ctx, _r, i = _item_of(item, acting=False)
	row = _held_row(i.held)
	path = media.staged_path(row.staged) if row else None
	if (not row or not (ctx.staff or row.uploader == ctx.user) or row.checking or row.scan_reason or not path
			or not os.path.exists(path)):
		raise frappe.DoesNotExistError(_("Not found"))
	with open(path, "rb") as fh:
		content = fh.read()
	shown = "inline" if row.ext in IMAGE_TYPES else "attachment"  # a photo was rebuilt from its pixels; others download
	return Response(content, status=200, content_type=mimetypes.guess_type(f"x.{row.ext}")[0] or "application/octet-stream",
		headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy":
		"same-origin", "Content-Disposition": f"{shown}; filename*=UTF-8''{quote(row.file_name or 'file')}"})


@frappe.whitelist(methods=["POST"])
def accept(item: str) -> dict:
	"""Staff who read the thread and did not upload it: the held file becomes a File in the request's folder, then the
	held row and its bytes go (after the commit); the item is Accepted, which may make the request Done."""
	from construction_core.discuss.api import lost_race_once

	return lost_race_once(lambda: _accept(item))


@frappe.whitelist(methods=["POST"])
def ask_again(item: str, reason: str) -> dict:
	"""The same callers as accept: the held file is deleted for real (D-389), the item is Waiting again with the
	reason, and the uploader is told (an email to a client, a bell to staff)."""
	from construction_core.discuss.api import lost_race_once

	why = _text(reason, MAX_REASON)
	if not why:
		frappe.throw(_("Say why the file is asked for again"))
	return lost_race_once(lambda: _ask_again(item, why))


@frappe.whitelist(methods=["POST"])
def nudge(request: str) -> dict:
	"""Staff: one reminder now to each person asked, while a required item is Waiting, counted toward their cap (4 for
	staff, 2 for clients, per request). Answers {reminded, at_cap}."""
	from construction_core.discuss.api import lost_race_once

	return lost_race_once(lambda: _nudge(request))


@frappe.whitelist(methods=["POST"])
def cancel(request: str) -> dict:
	"""The requester or the project's manager: the request is Cancelled and every held upload is deleted for real."""
	from construction_core.discuss.api import lost_race_once

	return lost_race_once(lambda: _cancel(request))


def _accept(item: str) -> dict:
	ctx, r, i = _review(item)
	row = _held_row(i.held)
	if not row or row.checking or row.scan_reason:
		frappe.throw(_("This file is still being checked, or it did not pass the check"))
	name = _store(r, row)
	frappe.db.set_value(ITEM, i.item, {"status": ACCEPTED, "file": name, "attachment": None}, update_modified=False)
	_drop_held(row, still_counts=False)  # its File counts toward the cap now
	_settle(r)
	_changed(r)
	return _page(ctx, _one(r.name))


def _ask_again(item: str, reason: str) -> dict:
	ctx, r, i = _review(item)
	frappe.db.set_value(ITEM, i.item, {"status": WAITING, "reason": reason, "attachment": None, "uploaded_by": None,
		"uploaded_on": None}, update_modified=False)
	row = _held_row(i.held)
	if row:
		_drop_held(row, still_counts=True)
	if is_client(i.uploaded_by):
		if may_ask(ctx.thread, i.uploaded_by):  # never mailed once they can no longer open the conversation
			_mail(r, i.uploaded_by, again=True)
	else:
		notify([i.uploaded_by], FILES_ASKED_AGAIN, frappe.get_doc(DOCTYPE, r.name), actor=ctx.user)
	_changed(r)  # never Done here: the person was just asked to send it again (only an accept settles a request)
	return _page(ctx, _one(r.name))


def _nudge(request: str) -> dict:
	ctx, r = _acting(request)
	if not ctx.staff:
		frappe.throw(_("The project team sends reminders"), frappe.PermissionError)
	out = {"reminded": 0, "at_cap": 0}
	if not _waiting(r):
		return out
	for rec in _recipient_rows(r.name):
		if cint(rec.reminders) >= cap_of(rec.user):
			out["at_cap"] += 1
		elif _remind(r, rec):
			out["reminded"] += 1
	return out


def _cancel(request: str) -> dict:
	ctx, r = _acting(request)
	if not (ctx.staff and (r.requested_by == ctx.user or actions.manages(ctx))):
		frappe.throw(_("Only the person who asked or the project's manager can cancel it"), frappe.PermissionError)
	_close(r)
	_changed(r)
	return _page(ctx, _one(r.name))


def _close(r) -> None:
	"""Every held upload deleted for real (D-389), its item Waiting again, the request Cancelled."""
	for i in r["items"]:
		row = _held_row(i.held)
		if row:
			_drop_held(row, still_counts=True)
	frappe.db.set_value(ITEM, {"parent": r.name, "parenttype": DOCTYPE, "status": RECEIVED}, {"status": WAITING,
		"attachment": None, "uploaded_by": None, "uploaded_on": None}, update_modified=False)
	frappe.db.set_value(DOCTYPE, r.name, "status", CANCELLED, update_modified=False)


def cancel_for(message: str) -> None:
	"""A removed card cannot be reviewed (actions.target refuses it), so its Open request goes with it, held uploads and
	all (discuss.edit.remove: the remover's own rights were checked there)."""
	name = frappe.db.get_value(DOCTYPE, {"message": message})
	r = _one(name, lock=True) if name else None
	if r and r.status == OPEN:
		_close(r)


def _settle(r) -> None:
	"""Done once every required item is Accepted and no item is Received (a held upload waits on review). Read under the
	request's lock, so a writer that committed since this transaction's first read is seen."""
	items = _one(r.name, lock=True)["items"]
	if all(x.item_status != RECEIVED and (x.item_status == ACCEPTED or not x.required) for x in items):
		frappe.db.set_value(DOCTYPE, r.name, "status", DONE, update_modified=False)


# --- reads and checks -----------------------------------------------------------------------------------------------


def _one(name, lock: bool = False):
	"""``lock``: a locking read, which sees the latest committed rows (a plain one shows the transaction's older snapshot)
	and holds the request's row until the commit."""
	found = requests([name], by="name", lock=lock) if isinstance(name, str) and name else []
	if not found:
		raise frappe.DoesNotExistError(_("Not found"))
	return found[0]


def _seen(name):
	"""(ctx, request) when the caller reads the request's card message now; one "not found" for missing and unseen."""
	viewer = frappe.session.user
	r = _one(name)
	if not frappe.get_list("Discuss Message", filters={"name": r.message, "removed": 0}, pluck="name", limit=1,
			user=viewer):
		raise frappe.DoesNotExistError(_("Not found"))
	t = read.thread_for(viewer, r.thread)
	return read.context(viewer, t), r


def _acting(name):
	"""(ctx, request) for a change: the card's message as the caller (discuss.actions.target: one "not found", the
	portal checks for a client, never a removed card or a Locked thread), the actions' rate limit, then the request
	read again under its row lock, so its writers go one at a time; it must be Open."""
	viewer = frappe.session.user
	actions.count(viewer)
	r = _one(name)
	ctx, _row = actions.target(viewer, r.message)
	frappe.db.sql(f"select name from `tab{DOCTYPE}` where name = %s for update", r.name)
	r = _one(r.name)
	if r.status != OPEN:
		frappe.throw(_("This file request is closed"))
	return ctx, r


def _item_of(item, acting: bool = True):
	"""(ctx, request, item row) for an item of a request the caller may see; one "not found" otherwise."""
	parent = frappe.db.get_value(ITEM, {"name": item, "parenttype": DOCTYPE}, "parent") \
		if isinstance(item, str) and item else None
	if not parent:
		raise frappe.DoesNotExistError(_("Not found"))
	ctx, r = (_acting if acting else _seen)(parent)
	return ctx, r, next(i for i in r["items"] if i.item == item)


def _review(item):
	"""(ctx, request, item) for accept and ask_again: staff who read the thread, not its uploader, on a Received item."""
	ctx, r, i = _item_of(item)
	if not ctx.staff:
		frappe.throw(_("The project team reviews these files"), frappe.PermissionError)
	if i.uploaded_by == ctx.user:
		frappe.throw(_("Someone else in the team reviews a file you sent"), frappe.PermissionError)
	if i.item_status != RECEIVED:
		frappe.throw(_("This file is not waiting for review"))
	return ctx, r, i


def _page(ctx: ViewCtx, r) -> dict:
	out = card(ctx, r)
	if out["role"] != "other":
		files, _revs = attachments.readable_files(ctx, [n for i in r["items"] for n in (i.example_file, i.file) if n])
		for item, i in zip(out["items"], r["items"]):
			item.update(example=_link(files.get(i.example_file)), file=_link(files.get(i.file)))
	asked = out["asked"] and may_ask(ctx.thread, ctx.user)
	out["may_upload"] = bool(out["may_upload"] and asked)
	left = max(0, client_files.DAILY_FILES - client_files.sent_today(r.project)[0]) if asked and not ctx.staff else None
	out.update(thread=r.thread, message=r.message, files_left_today=left)
	return out


def _changed(r) -> None:
	"""The card's readers are told, by ids after the commit (and the readers of a room mirror of it)."""
	actions.changed(frappe._dict(name=r.message, thread=r.thread, project=r.project, audience=r.audience,
		staff_only=r.staff_only), KEY)


def _link(f) -> dict | None:
	return {"file_name": f.file_name, "url": f.file_url} if f else None


def _json(value):
	try:
		return frappe.parse_json(value) if isinstance(value, str) else value
	except ValueError:
		return None


def _waiting(r) -> bool:
	return any(i.required and i.item_status == WAITING for i in r["items"])


def _recipient_rows(request: str) -> list:
	return frappe.get_all(RECIPIENT, filters={"parent": request, "parenttype": DOCTYPE},
		fields=["name", "user", "reminders", "last_reminded_on"], order_by="idx asc")


def cap_of(user: str) -> int:
	return CAPS["client" if is_client(user) else "staff"]


# --- held uploads ---------------------------------------------------------------------------------------------------


def _hold_for(r, item: str, attachment: str, user: str) -> None:
	"""The staged upload waits on its item: Held with no expiry, the item Received. Checked again under the request's
	lock, by a locking read that sees what committed during the scan: an item another upload filled meanwhile, or a
	request closed, refuses this one, and the rollback takes its staged bytes."""
	now = _one(r.name, lock=True)
	i = next(x for x in now["items"] if x.item == item)
	if now.status != OPEN or not _fillable(i):
		frappe.throw(_("This file is not waited for"))
	refused = _held_row(i.held)
	if refused:
		_drop_held(refused, still_counts=True)  # its scan said no: the new upload takes its place
	frappe.db.set_value(media.DOCTYPE, attachment, {"state": HELD, "expires_on": None}, update_modified=False)
	frappe.db.set_value(ITEM, item, {"status": RECEIVED, "attachment": attachment, "uploaded_by": user,
		"uploaded_on": now_datetime()}, update_modified=False)
	notify([now.requested_by], FILES_RECEIVED, frappe.get_doc(DOCTYPE, now.name), actor=user, coalesce=True)
	_changed(now)


def _held_row(name):
	return frappe.db.get_value(media.DOCTYPE, {"name": name, "state": HELD}, HELD_FIELDS, as_dict=True) if name else None


def _drop_held(row, still_counts: bool) -> None:
	"""Delete a held upload for real (D-389): the row now, its bytes and an unused preview after the commit.
	``still_counts``: a client's upload of today keeps counting toward the day's cap (D-182), as a discard does."""
	frappe.db.delete(media.DOCTYPE, {"name": row.name, "state": HELD})  # the server's own removal (ChatRow)
	if still_counts and sender_of(row.uploader) == "client" and getdate(row.creation) == getdate(nowdate()):
		client_files.count_discarded(row.project, row.file_size)
	path, digest = media.staged_path(row.staged), row.content_hash if row.has_preview else None

	def after():
		if path and os.path.exists(path):
			os.remove(path)
		if digest:
			media._drop_unused_preview(digest, media.preview_path(digest))

	frappe.db.after_commit.add(after)


def _store(r, row) -> str:
	"""The accepted File, from the bytes that were checked (their hash checked again), in the request's folder under the
	one-time claim shape client uploads in Files use (permissions.client_upload_shape): not shared, attached to the
	project, and the uploader's own, so a client reads it with the team until staff share it (D-158)."""
	from frappe.utils.file_manager import MaxFileSizeReachedError

	from construction_core.providers.storage import get_storage

	path = media.staged_path(row.staged)
	content = None
	if path and os.path.exists(path):
		with open(path, "rb") as fh:
			content = fh.read()
	if not content or get_content_hash(content) != row.content_hash:
		frappe.throw(_("This file is no longer waiting. Ask for it again."))
	attach = ("Construction Project", r.project)
	# validate_file allows exactly this one insert, as described here (permissions.client_upload_shape).
	frappe.flags.cc_client_upload = frappe._dict(project=r.project, folder=r.folder, visible=0, attach=attach,
		consumed=False)
	try:
		name = get_storage().put_own(r.folder.removeprefix(ROOT + "/"), row.file_name, content, r.project,
			attach=attach, cleaned=True)  # a folder's name is its path under Home
	except MaxFileSizeReachedError:
		frappe.throw(_("This file is too large to store. Ask for a smaller copy."))
	finally:
		frappe.flags.cc_client_upload = False
	frappe.db.set_value("File", name, "owner", row.uploader, update_modified=False)
	return name


# --- reminders ------------------------------------------------------------------------------------------------------


def remind() -> int:
	"""Daily (D-379, D-384): for each Open request, each person asked while a required item is Waiting, on the schedule
	(the day before the due date, on it, then every 2 days) up to their cap. A reminder dates its row, so a second run
	on the same day sends nothing. A request whose card was removed, or whose thread is Locked, gets none; one that
	fails never stops the others. Returns how many reminders went."""
	today_ = getdate(nowdate())
	sent = 0
	for name in frappe.get_all(DOCTYPE, filters={"status": OPEN, "due_on": ["<=", add_days(today_, 1)]}, pluck="name",
			order_by="due_on asc"):
		point = "cc_remind_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(point)
		try:
			sent += _remind_due(name, today_)
		except Exception:
			frappe.db.rollback(save_point=point)
			frappe.log_error(title="construction_core: file request reminders failed", reference_doctype=DOCTYPE,
				reference_name=name)
		else:
			frappe.db.release_savepoint(point)
	return sent


def _remind_due(name: str, today_) -> int:
	frappe.db.sql(f"select name from `tab{DOCTYPE}` where name = %s for update", name)  # one writer, as Nudge
	r = _one(name)
	if (r.status != OPEN or not _waiting(r) or not reminder_day(r.due_on, today_)
			or frappe.db.get_value("Discuss Message", r.message, "removed")
			or frappe.db.get_value("Discuss Thread", r.thread, "status") == "Locked"):
		return 0
	return sum(_remind(r, rec) for rec in _recipient_rows(name)
		if cint(rec.reminders) < cap_of(rec.user) and getdate(rec.last_reminded_on or "1900-01-01") != today_)


def reminder_day(due, today_) -> bool:
	"""The day before the due date, the day itself, then every EVERY days after it (D-379)."""
	days = date_diff(today_, due)
	return days in (-1, 0) or (days > 0 and days % EVERY == 0)


def _remind(r, rec) -> bool:
	"""One reminder, counted on the person's row: the email and, for staff, a bell notice. False when nothing reached
	them (no longer asked, notices and email off, no outgoing mail)."""
	if not may_ask(frappe._dict(name=r.thread, audience=r.audience, project=r.project), rec.user):
		return False
	sent = _mail(r, rec.user)
	if not is_client(rec.user):
		sent = bool(notify([rec.user], FILES_REMINDER, frappe.get_doc(DOCTYPE, r.name), actor=r.requested_by)) or sent
	if sent:
		frappe.db.set_value(RECIPIENT, rec.name, {"reminders": cint(rec.reminders) + 1, "last_reminded_on": nowdate()},
			update_modified=False)
	return sent


def _mail(r, user: str, again: bool = False) -> bool:
	"""The reminder (or the ask-again) email: who asks (the team, or the firm once its name is set) and a sign-in link
	to the request; never the project, the title or an item (D-160, D-175). Invitation words for clients (D-384)."""
	from frappe.desk.doctype.notification_settings.notification_settings import (
		is_email_notifications_enabled,
		is_notifications_enabled,
	)

	from construction_core import notifications
	from construction_core.onboarding.mail import _brand_args

	row = frappe.db.get_value("User", user, ["enabled", "email"], as_dict=True)
	if not (row and row.enabled and is_notifications_enabled(user) and is_email_notifications_enabled(user)
			and notifications._can_mail()):
		return False
	try:
		# now=False: Frappe's sender flushes the queue; the row names its request, never a conversation.
		frappe.sendmail(recipients=[row.email or user], subject=mail_subject(again), template="cc_file_request",
			args={**_brand_args(), "again": again, "link": sign_in_link(r, user)}, reference_doctype=DOCTYPE,
			reference_name=r.name, add_unsubscribe_link=0, now=False)
	except frappe.OutgoingEmailError:
		frappe.log_error(title=notifications.ERROR_TITLE, reference_doctype=DOCTYPE, reference_name=r.name)
		return False
	return True


def mail_subject(again: bool = False) -> str:
	"""Invitation words with no project or item (D-384); the firm leads once its name is set (D-401)."""
	from construction_core.onboarding.mail import brand

	if brand():
		words = _("The team at {0} would like a file from you again") if again else \
			_("The team at {0} would like a few files from you")
		return words.format(brand())
	return _("The team would like a file from you again") if again else _("The team would like a few files from you")


def sign_in_link(r, user: str) -> str:
	"""Through the sign-in page to the request, by ids only: the portal's for a client (D-265), the workspace's for
	staff: the room's page (the thread's own room, or the thread when it is one), and ``thread`` only for a thread inside
	a room (Discuss.vue reads both)."""
	if is_client(user):
		target = f"/portal/{quote(r.project, safe='')}?" + urlencode({"tab": "discuss", "thread": r.thread,
			"request": r.name})
		return get_url("/portal/login?redirect-to=" + quote(target, safe=""))
	in_room = frappe.db.get_value("Discuss Thread", r.thread, "in_room")
	query = {"request": r.name, **({"thread": r.thread} if in_room else {})}
	target = f"/workspace/{quote(r.project, safe='')}/discuss/{quote(in_room or r.thread, safe='')}?" + urlencode(query)
	return get_url("/login?redirect-to=" + quote(target, safe=""))


PART = Part(key=KEY, audiences=frozenset({"Internal", "Client"}), senders=frozenset({"staff"}), implies_kind=None,
	claim=claim, build=build, capable=capable, write=write)
