"""The attachments part (design §3.2, §3.3, §13.1 S1; P3-65): the files a message carries, and their cards.

Two sources draw the same card: Discuss Attachment rows (P3-65) and the legacy ``file`` field (P3-07, which the core
checks module guards because staff can set it by REST).

**Send.** ``upload`` (or ``attach``, from Files) stages a file as a Pending row of its uploader (discuss.media). The
send carries ``parts: {"attachments": [ids]}``. ``claim`` locks those rows (SELECT … FOR UPDATE) and accepts only rows of
the same user and thread that are pending and not expired, at most MAX_FILES; ``write`` then makes each File in the
conversation's folder and marks the row Sent. Neither call answers a File id (SEC-4, FIT-11).

**Who sends what** (rule 1). Clients send from a device, and link a file they read (Ask about this file), in an open
Client thread while the portal's Files section is on (FIT-19). Staff send in any open thread they read: in the Team
room a project file is linked (no copy, never shared, recheck N-3); in a Client thread it goes as a checked copy
(Share and send, D-367, D-390). Earlier versions and files in the bin are refused by the server. Partners join after
go-live (D-444).

**Caps** per sender kind (hub §7): clients 30 uploads in 10 minutes and the project's shared daily cap (50 files,
1 GiB); staff 60 in 10 minutes and no daily cap; two uploads at a time for everyone; 10 files a message.

**Cards** (§15.6) are drawn per viewer in two queries a page: the page's Sent rows, then the files with the download
rule checked per row in memory (readable_files), which also answers respond()'s ``_ref`` check, so a file the viewer
cannot read leaves no card (rule 2). The ``preview`` state, reason and IFC ``meta`` are the attachment row's own,
kept by the thumbs job (P3-75): a photo's preview from its own decode is ready at once; another type the renderer
reads is pending until its job ends; ``src`` is the one preview endpoint (previews.api). Staff also see the revision a
linked or copied file has now ("Rev B · now Rev C"), from the same query.

**Reads.** ``gallery`` is the conversation's files, through visible_messages and respond(). ``preview`` is P3-65's
address of the preview endpoint's ``attachment`` kind, kept for links already sent.
"""

import json
import os
import time
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from construction_core import client_files
from construction_core.discuss import checks, media, read
from construction_core.discuss import view as chat_view
from construction_core.discuss.registry import Part, SendCtx, ViewCtx, sender_of
from construction_core.permissions import client_section_open, refuse_closed, switches_once

MAX_FILES = 10  # per message (hub §7)
PREVIEW = "/api/method/construction_core.previews.api.image"  # P3-75: the one endpoint; P3-65's address still works
CARD_FIELDS = ["name", "message", "file", "source", "source_file", "kind", "ext", "file_size", "rev", "content_hash",
	"has_preview", "preview_w", "preview_h", "preview_state", "preview_reason", "preview_meta", "width", "height",
	"taken_on", "sent_on", "voice_length", "voice_type", "voice_codec", "voice_wave"]
FILE_FIELDS = ("name", "file_name", "file_url", "file_size")  # what a card shows; read as the viewer


# --- the send -------------------------------------------------------------------------------------------------------


def claim(ctx: SendCtx, value) -> list:
	"""The ids the sender staged, checked and locked; no writes. One refusal for any id that is not theirs to send."""
	if (not isinstance(value, list) or not 1 <= len(value) <= MAX_FILES
			or not all(isinstance(v, str) and v for v in value) or len(set(value)) != len(value)):
		frappe.throw(_("A message carries 1 to {0} files").format(MAX_FILES))
	if ctx.sender == "client" and not client_section_open("File", ctx.thread.project):
		# checked again at the send: the team may have switched Files off since the upload (FIT-19)
		frappe.throw(_("Sending files is switched off for this project"), frappe.PermissionError)
	found = locked(value)
	for name in value:
		r = found.get(name)
		if (not r or r.uploader != ctx.author or r.thread != ctx.thread.name or r.state != "Pending"
				or media.expired(r)):
			frappe.throw(_("A file is no longer waiting to be sent. Add it again."), frappe.PermissionError)
		if r.kind == "voice":  # P3-67: a voice note goes in its own part (parts.voice), never as a file
			frappe.throw(_("Send a voice note on its own."), frappe.PermissionError)
		if r.source == "Link" and ctx.sender == "staff" and ctx.thread.audience != "Internal":
			frappe.throw(_("A file is no longer waiting to be sent. Add it again."), frappe.PermissionError)
		if r.checking:  # P3-75 (D-417): a large file is sent only once its background scan says it is clean
			frappe.throw(_("{0} is still being checked for viruses. Send it when the check is done.").format(r.file_name))
		if r.scan_reason:  # refused by its background scan: never sent
			frappe.throw(_("{0} could not be sent: it did not pass the virus check. Take it out of the message.").format(
				r.file_name))
	return list(value)


def locked(names: list) -> dict:
	"""The waiting rows a send claims, locked (SELECT ... FOR UPDATE) until it commits: two sends cannot claim one."""
	return {r.name: r for r in frappe.db.sql(f"""select name, uploader, thread, state, expires_on, source, checking,
		scan_reason, file_name, kind from `tab{media.DOCTYPE}` where name in %s for update""", (tuple(names),),
		as_dict=True)}


def write(doc, value: list) -> None:
	"""Each claimed row becomes the message's: its File made (or its link checked again), then Sent with the content
	hash and revision it was sent with (R-32, §15.3)."""
	from construction_core.files import versions

	staged = {r.name: r for r in frappe.get_all(media.DOCTYPE, filters={"name": ["in", value]},
		fields=["name", "source", "file", "source_file", "file_name", "staged", "content_hash", "rev", "ext",
			"has_preview"])}
	sent_on = now_datetime()
	previews = []
	for position, name in enumerate(value):
		row = staged[name]
		changes = {"message": doc.name, "state": "Sent", "position": position, "sent_on": sent_on, "expires_on": None,
			"project": doc.project, "audience": doc.audience, "staff_only": doc.staff_only, "staged": None}
		if row.source == "Link":
			f = _linkable(row.file, doc.project, doc.author)
			if doc.audience == "Client" and not doc.staff_only and not f.cc_client_visible:
				frappe.throw(_("{0} is no longer shared with the client. Add it again.").format(row.file_name),
					frappe.PermissionError)
			changes.update(content_hash=f.content_hash, rev=versions.current_rev(f.name), file_size=f.file_size)
		else:
			if row.source == "Copy":  # Share and send: the team's file is checked again, and must be the revision copied
				source = _linkable(row.source_file, doc.project, doc.author, _("{0} is no longer in the project's files, or you "
					"cannot open it. Add it again.").format(row.file_name))
				if versions.current_rev(source.name) != row.rev:
					frappe.throw(_("{0} has a new revision since it was added. Add it again to send the new one.")
						.format(row.file_name), frappe.ValidationError)
			changes["file"] = media.materialize(row, doc)
		changes.update(_preview_state(row))
		if changes.get("preview_state") == "pending":
			previews.append((changes["file"] if "file" in changes else row.file, changes.get("content_hash")
				or row.content_hash, row))
		frappe.db.set_value(media.DOCTYPE, name, changes, update_modified=False)
	_ask_previews(previews)


def _preview_state(row) -> dict:
	"""What a card shows until its preview is made (§15.6): a photo with its own preview keeps it (P3-65); a type the
	renderer reads is pending; any other type has none, for a reason (P3-75)."""
	from construction_core.previews.jobs import previewable

	if row.has_preview:
		return {}
	if previewable(row.ext):
		return {"preview_state": "pending", "preview_reason": None}
	return {"preview_state": "skipped", "preview_reason": "not_supported"}


def _ask_previews(sent: list) -> None:
	"""The thumbs job for each sent file, queued after the commit; bytes already drawn answer at once (a twin)."""
	from construction_core.previews import jobs, store
	from construction_core.previews.sources import Target

	for file, digest, row in sent:
		row_ = jobs.request(Target("File", file, digest, row.ext or "", scanned=row.source in ("Upload", "Copy")))
		if row_ and row_.state in store.FINAL:
			store.sync_attachments(row_, row_.state, row_.reason, row_.width, row_.height, row_.info)


def _linkable(file: str, project: str, user: str, refusal: str | None = None):
	"""A linked file (or a copy's source) is checked again at send: still this project's, current, not in the bin, and
	the sender reads it. ``refusal``: the words when it is not."""
	f = frappe.db.get_value("File", file, ["name", "file_name", "file_size", "content_hash", "cc_project", "is_folder",
		"cc_trashed", "cc_version_of", "cc_client_visible"], as_dict=True) if file else None
	if (not f or f.is_folder or f.cc_project != project or f.cc_trashed or f.cc_version_of
			or not frappe.has_permission("File", "read", doc=f.name, user=user, throw=False)):
		frappe.throw(refusal or _("A file is no longer waiting to be sent. Add it again."), frappe.PermissionError)
	return f


# --- the cards ------------------------------------------------------------------------------------------------------


def build(ctx: ViewCtx, rows: list) -> dict:
	"""{message: [card]} for the files ``ctx.user`` may read, from the page's one read (``page``). A voice note's row
	is drawn by parts.voice from the same read."""
	got = page(ctx, rows)
	if not got:
		return {}
	cards = {}
	for message, file in got.legacy.items():
		if file in got.files:
			cards.setdefault(message, []).append(_legacy_card(got.files[file]))
	for a in got.attached:
		if a.file in got.files and a.kind != "voice":
			cards.setdefault(a.message, []).append(card(ctx, a, got.sent.get(a.name) or got.files[a.file], got.now))
	return cards


def page(ctx: ViewCtx, rows: list):
	"""The page's Sent rows in one query and the files as the viewer in one more (with, for staff, the revisions
	linked and copied files have now), read once per page for the attachments and the voice parts both (P3-67: a
	voice card adds no query). None when the page carries no file."""
	if not ctx.thread.get("name"):
		return None  # the inbox's last-message line (P3-74): it shows the kind, never a card, and reads nothing more
	key = ("attachments page", tuple(r.name for r in rows))
	if key not in ctx.memo:
		ctx.memo[key] = _read_page(ctx, rows)
	return ctx.memo[key]


def _read_page(ctx: ViewCtx, rows: list):
	with_rows = [r.name for r in rows if r.get("kind") in ("Files", "Voice", "Poll")]  # P3-68: a poll's pictures
	attached = frappe.get_all(media.DOCTYPE, filters={"message": ["in", with_rows], "state": "Sent"},
		fields=CARD_FIELDS, order_by="position asc, creation asc") if with_rows else []
	legacy = {r.name: r.file for r in rows if r.get("file")}
	names = [a.file for a in attached if a.file] + list(legacy.values())
	if not names:
		return None
	sources = [a.source_file or a.file for a in attached if a.source_file or a.source == "Link"] if ctx.staff else []
	files, revs = readable_files(ctx, names, also=sources)
	sent = _sent_revisions(ctx, [a for a in attached if a.source == "Link" and a.file in files and a.content_hash
		and files[a.file].content_hash != a.content_hash], files)
	return frappe._dict(attached=attached, legacy=legacy, files=files, now={n: revs[n] for n in sources if n in revs},
		sent=sent)


def _sent_revisions(ctx: ViewCtx, moved: list, files: dict) -> dict:
	"""{attachment: the version File it was sent as} for linked files that have a new revision since (R-32, §15.3: a
	card shows the revision that was sent). The sent bytes are kept by the version row with that content hash
	(P3-43, D-305); a reader who cannot read that version (a client, D-301) gets the current file instead. One query
	for the versions and one for their files, only on a page that has such a card."""
	if not moved:
		return {}
	versions = {}
	for v in frappe.get_all("File", filters={"cc_version_of": ["in", list({a.file for a in moved})],
			"content_hash": ["in", list({a.content_hash for a in moved})]}, fields=["name", "cc_version_of",
			"content_hash"], order_by="creation desc"):
		versions.setdefault((v.cc_version_of, v.content_hash), v.name)
	wanted = {a.name: versions.get((a.file, a.content_hash)) for a in moved}
	readable, _revs = readable_files(ctx, [v for v in wanted.values() if v])
	return {name: frappe._dict(readable[v], file_name=files[a.file].file_name) for a in moved
		for name, v in [(a.name, wanted[a.name])] if v in readable}


def readable_files(ctx: ViewCtx, names, also=(), rows=None) -> tuple[dict, dict]:
	"""{name: File row} of ``names`` that ``ctx.user`` may read, in one query, each answer also in ``ctx.memo`` so
	respond()'s ``_ref`` check asks nothing more. A list read cannot be used: Frappe's own File list rule limits every
	non-System user to the files they own, and for staff it costs some twenty queries (measured, P3-65). So each row is
	checked here with the two rules a download uses, without a query per file: ours (permissions.can_access, whose
	switches are read once per request under switches_once) and Frappe's File rule (public or the owner's own, else
	the record it is attached to, read once per record type, else a share, read once for the page only when needed).
	test_discuss_attachments checks it against has_permission.
	``also``: files whose revision letter staff see on a card ("now Rev C"), read in the same query and returned as
	{name: letter} beside the readable rows; they are never marked readable.
	``rows``: the File rows already read with these fields in the caller's own query (P3-66: records.resolve reads them in
	its one statement with the records); the rule is the same."""
	from construction_core.files import versions
	from construction_core.permissions import can_access

	names = [n for n in dict.fromkeys(names) if n]
	wanted = list(dict.fromkeys([*names, *(n for n in also if n)]))
	if rows is None:
		rows = frappe.get_all("File", filters={"name": ["in", wanted]}, fields=[*FILE_FIELDS, "owner", "is_private",
			"is_folder", "cc_project", "cc_client_visible", "cc_trashed", "cc_version_of", "attached_to_doctype",
			"attached_to_name", "cc_rev", "content_hash"]) if wanted else []
	found, revs, cards, shared, waiting = {}, {}, set(names), None, []
	for f in rows:
		revs[f.name] = f.cc_rev or versions.letter(1)
		if f.name not in cards:
			continue
		f.doctype = "File"
		if not (not f.is_folder and f.cc_project and can_access(f, "read", ctx.user)):
			ctx.memo[("File", f.name, ctx.user)] = False
		elif ctx.user == "Administrator" or not f.is_private or f.owner == ctx.user:
			ctx.memo[("File", f.name, ctx.user)] = True
			found[f.name] = f
		else:
			waiting.append(f)
	_records(ctx, waiting)
	for f in waiting:
		ok = bool(f.attached_to_doctype and f.attached_to_name
			and ctx.memo.get((f.attached_to_doctype, f.attached_to_name, ctx.user)))
		if not ok:
			if shared is None:  # Frappe's rule also opens a file shared with the reader: one read for the page
				shared = set(frappe.share.get_shared("File", ctx.user, ["read"], filters=[["share_name", "in", names]]))
			ok = f.name in shared
		ctx.memo[("File", f.name, ctx.user)] = ok
		if ok:
			found[f.name] = f
	for n in names:
		ctx.memo.setdefault(("File", n, ctx.user), False)
	return found, revs


def _records(ctx: ViewCtx, files) -> None:
	"""Frappe's File rule for files that are neither public nor the reader's own: the reader reads the record each is
	attached to. A type with one record on the page (the usual page: its thread, its project) is checked on its cached
	document; a type with more is read once as the viewer (ViewCtx.readable, the list form of the same predicate, as the
	pointer part reads its targets), whatever the number of files or records."""
	wanted = {}
	for f in files:
		if f.attached_to_doctype and f.attached_to_name and (f.attached_to_doctype, f.attached_to_name,
				ctx.user) not in ctx.memo:
			wanted.setdefault(f.attached_to_doctype, []).append(f.attached_to_name)
	for doctype, records in wanted.items():
		records = list(dict.fromkeys(records))
		if len(records) == 1:
			_one_record(ctx, doctype, records[0])  # the usual page: the conversation's thread, or the project
			continue
		try:
			ctx.readable(doctype, records)
		except frappe.PermissionError:  # no role reads this type: none of its records is readable
			frappe.clear_last_message()
			for n in records:
				ctx.memo[(doctype, n, ctx.user)] = False


def _one_record(ctx: ViewCtx, doctype: str, name: str) -> None:
	"""One record's read rule on its cached document: the same has_permission, without loading the record again. What
	the rule reads of it is set once (a thread's project and audience) or kept fresh by the cache (a project's
	members); membership itself was checked from the user's own rows by can_access."""
	try:
		record = frappe.get_cached_doc(doctype, name)
	except frappe.DoesNotExistError:
		frappe.clear_last_message()
		record = None
	ctx.memo[(doctype, name, ctx.user)] = bool(record and frappe.has_permission(doctype, "read", doc=record,
		user=ctx.user, throw=False))


def card(ctx: ViewCtx, a, f, now: dict) -> dict:
	"""One card (§15.6): the file's name, address and size, its kind and badge, the preview contract and, for a photo,
	its capture time; ``_ref`` for respond(). No File id, no source file and no hash leave."""
	size = cint(a.file_size or f.file_size)
	out = {"_ref": ("File", f.name), "attachment": a.name, "file_name": f.file_name, "url": f.file_url, "size": size,
		"kind": a.kind or "file", "badge": {"type": client_files.LABEL.get(a.ext, (a.ext or "").upper()),
			"size": client_files.size_text(size), "rev": a.rev or None},
		"preview": preview_of(a), "taken_on": str(a.taken_on) if a.taken_on else None,
		"sent_on": str(a.sent_on) if a.sent_on else None, "width": a.width or None, "height": a.height or None}
	if out["preview"]["state"] == "none":
		out["reason"] = a.preview_reason or ("failed" if a.kind == "photo" else "not_supported")
	if a.preview_meta:
		out["meta"] = _meta(a.preview_meta)
	if ctx.staff:
		current = now.get(a.source_file or (a.file if a.source == "Link" else None))
		out["rev_now"] = current if current and current != a.rev else None
	return out


def preview_of(a) -> dict:
	"""The card's preview from the attachment's own row (the thumbs job keeps it up to date): no query of its own."""
	if a.has_preview:
		return {"state": "ready", "src": f"{PREVIEW}?kind=attachment&name={a.name}", "w": a.preview_w, "h": a.preview_h}
	return {"state": "pending" if a.get("preview_state") == "pending" else "none", "src": None, "w": None, "h": None}


def _meta(raw) -> dict | None:
	try:
		value = json.loads(raw)
	except (TypeError, ValueError):
		return None
	return value if isinstance(value, dict) else None


def _legacy_card(f) -> dict:
	"""A P3-07 message's ``file``: the card it always had (its name and address; test_client_uploads pins the shape).
	The screen draws it with no preview."""
	return {"_ref": ("File", f.name), "file_name": f.file_name, "url": f.file_url}


def capable(ctx: ViewCtx, thread) -> bool:
	"""Whether the viewer's composer offers files here; the thread row only, so a list of threads costs nothing more.
	A client sends while the portal's Files section is on (FIT-19); staff in any open thread (F5)."""
	if thread.status == "Locked" or thread.audience not in PART.audiences:
		return False
	if ctx.staff:
		return True
	if thread.audience != "Client":
		return False
	key = ("Files section", thread.project)  # one answer per project for a whole thread list
	if key not in ctx.memo:
		ctx.memo[key] = client_section_open("File", thread.project)
	return ctx.memo[key]


# --- the endpoints --------------------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def upload(thread: str, taken_on: str | None = None, voice: int | str | None = None) -> dict:
	"""Stage one file from this device (§3.2). ``taken_on``: the capture time the browser read before its own shrink
	dropped the EXIF; the file's own EXIF time wins. ``voice``: the file is a voice note (P3-67, parts.voice): its name
	is the server's and its type is read from its bytes. Answers the waiting file, never a File id."""
	started = time.monotonic()
	frappe.form_dict.pop("file_size", None)  # File.validate would take it over the real size
	t, sender = _place(thread)
	user = frappe.session.user
	client_files.check_burst(user, None if sender == "client" else client_files.STAFF_BURST)
	if sender == "client":
		from construction_core.discuss.send import check_rate  # here: send imports the parts

		check_rate(user)  # P3-63 audit: a message the limit would refuse costs no scan (not counted here)
	with media.slot(user), _room_types(sender, t), _voice_types(cint(voice)):
		display, ext, content = _one_voice() if cint(voice) else _one_file()
		if len(content) > client_files.SCAN_IN_REQUEST:  # D-417: a large model file is scanned after the request
			with client_files.large_slot():
				content = _checked_but_scan(ext, content, t.project, client=sender == "client")
				name = media.stage(t, user, display, ext, content, taken=_taken(taken_on))
				_hold(name)
		else:
			facts = {}
			content = media.checked(ext, content, t.project, started=started, client=sender == "client", facts=facts)
			name = media.stage(t, user, display, ext, content, taken=_taken(taken_on), voice=facts.get("voice"))
	return waiting(name)


@frappe.whitelist(methods=["POST"])
def attach(thread: str, file: str | None = None, url: str | None = None) -> dict:
	"""Attach a project file (Attach from Files, Ask about this file, §3.2). Staff name the ``file``; a client names the
	address their Files tab shows (``url``), never an id. A file that is missing, of another project, an earlier
	version, in the bin or unreadable answers the same "not found". In a Client thread staff send a checked copy
	("Share and send"); elsewhere the file is linked, never copied or shared."""
	started = time.monotonic()
	t, sender = _place(thread)
	user = frappe.session.user
	limit = None if sender == "client" else client_files.STAFF_BURST
	f = _project_file(t, sender, file, url)
	if sender == "client" or t.audience == "Internal":
		client_files.check_burst(user, limit, what="link")  # every link counts, apart from the scans
		return waiting(media.link(t, user, f))
	from construction_core.files import versions

	client_files.check_burst(user, limit)  # a checked copy is scanned like an upload
	with media.slot(user):
		display, ext = client_files.clean_name(f.file_name)
		content = frappe.get_doc("File", f.name).get_content()
		content = content.encode() if isinstance(content, str) else content
		later = len(content) > client_files.SCAN_IN_REQUEST  # D-417: a large model file is scanned after the request
		content = (_checked_but_scan(ext, content, t.project, client=False) if later
			else media.checked(ext, content, t.project, started=started, client=False))
		name = media.stage(t, user, display, ext, content, source="Copy", source_file=f.name,
			rev=versions.current_rev(f.name))
		if later:
			_hold(name)
	return waiting(name)


@frappe.whitelist(methods=["POST"])
def discard(attachment: str) -> None:
	"""Take a waiting file out of the composer: the uploader's own Pending row only, deleted with its bytes (D-389)."""
	row = frappe.db.get_value(media.DOCTYPE, attachment, ["name", "uploader", "state", "staged", "content_hash",
		"has_preview", "project", "source", "file_size"], as_dict=True) if isinstance(attachment, str) and attachment 		else None
	if not row or row.uploader != frappe.session.user or row.state != "Pending":
		raise frappe.DoesNotExistError(_("Not found"))
	if row.source != "Link" and sender_of(row.uploader) == "client":
		client_files.count_discarded(row.project, row.file_size)  # still today's: a discard frees no daily cap
	media.remove(row)


@frappe.whitelist(methods=["GET"])
def gallery(thread: str, cursor: str | None = None, limit: int | str = 50) -> dict:
	"""Files in this conversation (§3.2): the viewer's own visible messages that carry files, newest first, as cards
	through the one exit. A thread the viewer cannot read answers like a missing one."""
	with switches_once():
		viewer = frappe.session.user
		t = read.thread_for(viewer, thread)
		ctx = read.context(viewer, t)
		size = read.page_limit(limit)
		fields = read.STAFF_FIELDS if ctx.staff else read.FIELDS
		rows = read.visible_messages(viewer, t.name, cursor, size + 1, fields, only={"kind": "Files", "removed": 0})
		more, rows = len(rows) > size, rows[:size]
		out = {"messages": chat_view.present(ctx, rows), "cursor": rows[-1].name if more else None}
		return chat_view.respond(out, viewer, memo=ctx.memo)


@frappe.whitelist(methods=["GET"])
def preview(attachment: str):
	"""P3-65's preview address, kept for the cards and links already sent: the one endpoint's ``attachment`` kind
	(previews.api, P3-75), which checks the message (the visible set) and the file (the source, SEC-8)."""
	from construction_core.previews import api as previews

	return previews.serve("attachment", attachment)


@frappe.whitelist(methods=["GET"])
def file_of(attachment: str) -> dict:
	"""Staff only: the File a sent card opens, for the P3-48 viewer (§3.2: staff open files in the viewer). The card
	itself never carries a File id; a client is refused like a missing card. The same checks as the card: the viewer
	reads the message (the visible set) and the file; a linked file revised since opens as the revision that was sent
	when that version still exists (R-32)."""
	viewer = frappe.session.user
	if sender_of(viewer) != "staff":
		raise frappe.DoesNotExistError
	row = frappe.db.get_value(media.DOCTYPE, attachment, ["message", "file", "state", "source", "content_hash"],
		as_dict=True) if isinstance(attachment, str) and attachment else None
	if not row or row.state != "Sent" or not row.message or not row.file:
		raise frappe.DoesNotExistError
	visible = frappe.get_list("Discuss Message", filters={"name": row.message}, pluck="name", limit=1, user=viewer)
	name = row.file
	if not frappe.db.exists("File", name):  # deleted: the same answer as any other, and no File id in it (P3-75 audit)
		raise frappe.DoesNotExistError
	if row.source == "Link" and row.content_hash and frappe.db.get_value("File", name, "content_hash") != row.content_hash:
		name = frappe.db.get_value("File", {"cc_version_of": row.file, "content_hash": row.content_hash}, "name") or name
	if not visible or not frappe.has_permission("File", "read", doc=name, user=viewer, throw=False):
		raise frappe.DoesNotExistError
	f = frappe.db.get_value("File", name, ["name", "file_name", "file_url", "cc_rev", "content_hash", "cc_client_visible"],
		as_dict=True)
	return {"name": f.name, "file_name": f.file_name, "url": f.file_url, "rev": f.cc_rev or "A",
		"content_hash": f.content_hash or "", "client_visible": f.cc_client_visible}


def waiting(name: str) -> dict:
	"""What the composer shows of a waiting file: its id for the send, name, size, kind and capture time; ``checking``
	while a large file's background scan runs (P3-75: "Checking…"), and ``reason`` once it was refused."""
	r = frappe.db.get_value(media.DOCTYPE, name, ["name", "file_name", "file_size", "kind", "taken_on", "expires_on",
		"checking", "scan_reason"], as_dict=True)
	out = {"attachment": r.name, "file_name": r.file_name, "size": cint(r.file_size), "kind": r.kind,
		"taken_on": str(r.taken_on) if r.taken_on else None, "expires_on": str(r.expires_on)}
	if r.checking:
		out["checking"] = True
	if r.scan_reason:
		out["reason"] = r.scan_reason
	return out


@frappe.whitelist(methods=["GET"])
def checking(attachments: str) -> dict:
	"""{id: {checking, reason}} for the uploader's own waiting files, so the composer can turn "Checking…" into a file
	ready to send, or into "could not be checked" / "a threat was found" (reason). Anyone else's id, or one no longer
	waiting, is left out."""
	ids = frappe.parse_json(attachments) if isinstance(attachments, str) else None
	if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_FILES or not all(isinstance(i, str) for i in ids):
		frappe.throw(_("A message carries 1 to {0} files").format(MAX_FILES))
	rows = frappe.get_all(media.DOCTYPE, filters={"name": ["in", ids], "uploader": frappe.session.user,
		"state": "Pending"}, fields=["name", "checking", "scan_reason"])
	return {r.name: {"checking": bool(r.checking), "reason": r.scan_reason or None} for r in rows}


def scan_staged(attachment: str) -> None:
	"""The background scan of a large waiting file (D-417), with the held Files sends' policy (scan_holds). Clean: it
	may be sent. A threat, a file clamd cannot fully check, or a scan that could not run in MAX_TRIES tries: its bytes
	go and the waiting row keeps the reason, so the composer says why (it still counts today); it cannot be sent."""
	from construction_core import scan_holds

	row = frappe.db.get_value(media.DOCTYPE, attachment, ["name", "uploader", "state", "staged", "project", "file_size",
		"checking", "scan_tries", "content_hash"], as_dict=True)
	path = media.staged_path(row.staged) if row else None
	if not row or row.state not in ("Pending", "Held") or not row.checking:  # Held: a file request's upload (P3-71)
		return
	if not path or not os.path.exists(path):
		return _refuse_staged(row, scan_holds.NOT_STORED)
	with open(path, "rb") as fh:
		content = fh.read()
	verdict = scan_holds.scan(content, row.project)
	if verdict == "later":
		if scan_holds.gives_up(row.scan_tries):
			return _refuse_staged(row, scan_holds.COULD_NOT_CHECK)
		frappe.db.set_value(media.DOCTYPE, row.name, "scan_tries", cint(row.scan_tries) + 1, update_modified=False)
		return
	if verdict:
		return _refuse_staged(row, verdict)
	frappe.db.set_value(media.DOCTYPE, row.name, "checking", 0, update_modified=False)


def _refuse_staged(row, reason: str) -> None:
	path = media.staged_path(row.staged)
	frappe.db.set_value(media.DOCTYPE, row.name, {"checking": 0, "scan_reason": reason, "staged": None},
		update_modified=False)
	frappe.db.after_commit.add(lambda: path and os.path.exists(path) and os.remove(path))


def rescan_due() -> int:
	"""Every five minutes: large waiting files whose scan could not run are queued again (scan_holds.MAX_TRIES in all),
	and so are those whose first job was lost (scan_holds.LOST_MINUTES). An upload left waiting expires in a day."""
	from construction_core import scan_holds

	waiting = {"state": ["in", ("Pending", "Held")], "checking": 1}  # Held: a file request's upload (P3-71)
	rows = frappe.get_all(media.DOCTYPE, filters={**waiting, "scan_tries": [">", 0]}, pluck="name", limit=50)
	rows += frappe.get_all(media.DOCTYPE, filters={**waiting, "scan_tries": 0, "creation": ["<", add_to_date(
		now_datetime(), minutes=-scan_holds.LOST_MINUTES)]}, pluck="name", limit=50)
	for name in dict.fromkeys(rows):
		_queue_scan(name, again=True)
	return len(set(rows))


def _hold(name: str) -> None:
	frappe.db.set_value(media.DOCTYPE, name, "checking", 1, update_modified=False)
	_queue_scan(name)


def _queue_scan(name: str, again: bool = False) -> None:
	"""The scan job on the thumbs queue (scan_holds.queue): after the commit for a new upload, at once for a retry."""
	from construction_core import scan_holds

	scan_holds.queue("construction_core.discuss.parts.attachments.scan_staged", after_commit=not again, attachment=name)


def _checked_but_scan(ext: str, content: bytes, project: str, *, client: bool) -> bytes:
	"""media.checked's steps but the scan, in its order, for a file the scan cannot finish in the request."""
	client_files.check_type(ext)
	client_files.check_signature(ext, content)
	limit = client_files.client_limit()
	if len(content) > limit:
		frappe.throw(_("The file is larger than {0}").format(client_files.size_text(limit)))
	if client:
		client_files.check_daily_cap(project, len(content), chat=True)
	client_files.check_structure(ext, content)
	return content


@contextmanager
def _room_types(sender: str, thread):
	"""In the Team room the team also sends the types the design allows staff there (client_files.STAFF_ROOM_TYPES)."""
	if sender == "staff" and thread.audience == "Internal":
		with client_files.staff_room_types():
			yield
	else:
		yield


@contextmanager
def _voice_types(voice: int):
	if voice:
		with client_files.voice_types():
			yield
	else:
		yield


def _one_voice() -> tuple[str, str, bytes]:
	from construction_core.discuss.parts import voice  # here: voice imports this module

	return voice.incoming(_upload_part())


def _place(thread):
	"""The thread a file is staged for, with the send's own checks for the sender kind (rule 3), and the Files switch
	for a client (FIT-19). Returns (thread, sender)."""
	sender = sender_of(frappe.session.user)
	if not isinstance(thread, str) or not thread:
		frappe.throw(_("Choose a conversation"))
	if not frappe.db.exists("Discuss Thread", thread):
		raise frappe.DoesNotExistError(_("Not found"))
	t = frappe.get_doc("Discuss Thread", thread)
	try:  # a thread the sender cannot read answers like a missing one (send_file's step 3, SEC-22)
		if sender == "client":
			checks.client_send(t)
		else:
			t.check_permission("read")
	except frappe.PermissionError:
		frappe.clear_last_message()
		raise frappe.DoesNotExistError(_("Not found")) from None
	refuse_closed(t.project)  # P3-59: after the read checks, so the refusal tells no outsider the project is closed
	if sender == "client" and not client_section_open("File", t.project):
		frappe.throw(_("Sending files is switched off for this project"), frappe.PermissionError)
	if t.status == "Locked":
		frappe.throw(_("This thread is locked"))
	if t.audience not in PART.audiences:
		frappe.throw(_("You cannot post in this thread"), frappe.PermissionError)
	return t, sender


def _one_file() -> tuple[str, str, bytes]:
	"""The request's one file part, named "file", read up to the limit plus one byte."""
	part = _upload_part()
	display, ext = client_files.clean_name(part.filename)
	client_files.check_type(ext)
	return display, ext, part.stream.read(client_files.client_limit() + 1)


def _upload_part():
	request = getattr(frappe.local, "request", None)
	got = list(request.files.items(multi=True)) if request is not None and request.files else []
	if len(got) > 1 or (got and got[0][0] != "file"):
		frappe.throw(_("Choose one file to send"))
	if not got:
		frappe.throw(_("Choose a file to send"))
	return got[0][1]


def _project_file(t, sender: str, file, url):
	"""The project file to attach, read as the sender. One answer for every refusal."""
	user = frappe.session.user
	if sender == "client":
		filters = {"file_url": url, "cc_project": t.project} if isinstance(url, str) and url.startswith("/") else None
	else:
		filters = {"name": file, "cc_project": t.project} if isinstance(file, str) and file else None
	# Candidates by name or address, then the download rule for each (a list read as a client sees only the client's
	# own files: Frappe's File list rule). One address can name several rows: Frappe keeps identical bytes once, so a
	# second upload of the same file shares the first one's address. The reader's readable current row is linked, a
	# shared one first (every reader of the conversation who may see it then does).
	found = frappe.get_all("File", filters=filters, fields=["name", "file_name", "file_size", "content_hash",
		"is_folder", "cc_trashed", "cc_version_of", "cc_project", "cc_client_visible"], order_by="cc_client_visible desc,"
		" creation asc", limit=20) if filters else []
	f = next((r for r in found if not (r.is_folder or r.cc_trashed or r.cc_version_of or r.cc_project != t.project)
		and (sender != "client" or r.cc_client_visible)  # a client links only what the team shared (every client reads it)
		and frappe.has_permission("File", "read", doc=r.name, user=user, throw=False)), None)
	if not f:
		raise frappe.DoesNotExistError(_("This file cannot be attached"))
	return f


def _taken(value):
	"""The browser's capture time, used only when the image itself has none: a plausible past time, else nothing."""
	try:
		taken = get_datetime(value) if isinstance(value, str) and value else None
	except Exception:
		return None
	if not taken:
		return None
	if taken.tzinfo:  # an aware time is the same moment on the site's clock; a naive one is the camera's wall time
		from zoneinfo import ZoneInfo

		from frappe.utils import get_system_timezone

		taken = taken.astimezone(ZoneInfo(get_system_timezone()))
	taken = taken.replace(tzinfo=None)
	# up to 14 hours ahead of the site's clock: a camera's wall time in a zone east of the site (the site keeps one zone)
	return taken if 1990 <= taken.year and taken <= add_to_date(now_datetime(), hours=14) else None


PART = Part(key="attachments", audiences=frozenset({"Internal", "Client"}), senders=frozenset({"staff", "client"}),
	implies_kind="Files", claim=claim, build=build, capable=capable, write=write)
