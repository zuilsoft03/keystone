"""One message write path (D-358, design §13.1 S2). Every entry calls send_impl: discuss.api.post and send (staff, and
the rule-3 client branch) and DiscussChat.post (portal.post_message); a message of files carries the attachments part.

send_impl does, in order: the checks for the account kind (from the session), parsing ``parts``, then the insert
under a request-local claim. The claim is the one way a client insert is accepted (D-387: clients have no create),
and DiscussMessage.before_insert consumes it once. This module is the only one that sets it. A retried send with the
same ``client_id`` returns the first message (F8) and is not counted again. The per-user rate limit is counted in
before_insert, so a REST insert counts too (D-412).

The server's System flag (D-419, §13.5 item 3) is set here too, by post_system only: kind System exists only under
it, with the one neutral text and an author the server names, and a REST insert claiming System comes back as Text.

"Also send to room" (§14.2) is a mirror made in the same call, after the claimed reply: a System message in the room
pointing at the reply, by the reply's author. It takes no second claim, is never rate-counted, carries no mention and
tells no one by a notice; a retry with the reply's client_id returns the reply, whose mirror was made with it. The
checks accept a mirror only of a reply made in this request, in a thread of that room, that is no staff-only note.

The closed-project refusal is P3-59's (D-409).
"""

from functools import partial

import frappe
from frappe import _
from frappe.utils import cint

from construction_core.discuss import checks, parts
from construction_core.discuss.parts import pointer
from construction_core.discuss.registry import SYSTEM_TEXT, SendCtx, derive_kind, sender_of
from construction_core.permissions import _bypass

CLAIM = "cc_discuss_write"
SYSTEM = "cc_discuss_system"
# Messages per user per minute, by sender kind (SEC-21, D-411). Partners join the client bucket with P3-32.
RATES = {"client": 30, "staff": 120}
RATE_WINDOW = 60


def send_impl(thread: str, text: str, client_id: str | None = None, staff_only=0, parts_in=None,
		file: str | None = None, counted: bool = True, also_room=0) -> str:
	"""``counted=False``: send_file's second try after a 1020, whose first try was counted already. ``also_room``: the
	reply also shows in its room's timeline (a mirror)."""
	user = frappe.session.user
	sender = sender_of(user)
	t = _thread(thread, sender)
	staff_only, also_room = cint(staff_only), cint(also_room)
	if sender == "client" and staff_only:
		frappe.throw(_("Staff-only notes are for the project team"), frappe.PermissionError)
	if also_room and (staff_only or not t.in_room):
		frappe.throw(_("Only a shared reply in a thread can also go to the room"))
	claimed = parse_parts(parts_in)
	text = checks.text(text, empty=bool(claimed or file))  # a message of files needs no caption (P3-65, rule 2)
	client_id = checks.client_id(client_id)
	first = _first(user, client_id, t.name)
	if first:
		return first
	name = _insert(t, user, sender, text, client_id, staff_only, claimed, file, counted)
	if also_room and name in (frappe.flags.get(checks.SENT) or ()):  # not a race's winner: its request mirrored it
		post_system(t.in_room, user, [("Discuss Message", name)], mirror=name)
	return name


def parse_parts(value) -> dict:
	"""``parts`` is a JSON object keyed by registered part keys (D-392); anything else is refused."""
	if value in (None, "", {}):
		return {}
	try:
		value = frappe.parse_json(value)
	except ValueError:
		value = None
	if not isinstance(value, dict):
		frappe.throw(_("The message parts are not valid"))
	known = parts.by_key()
	unknown = [k for k in value if k not in known]
	if unknown:
		frappe.throw(_("This message has a part that cannot be sent: {0}").format(unknown[0]))
	return value


def take_claim(doc):
	"""Called by DiscussMessage.before_insert: the claim, consumed, when it is this insert's; else None."""
	claim = frappe.flags.get(CLAIM)
	if not claim or claim.consumed:
		return None
	if (claim.thread, claim.author, claim.client_id) != (doc.thread, frappe.session.user, doc.client_id):
		return None
	claim.consumed = True
	return claim


def post_system(thread: str, author: str, targets=(), creation=None, quiet: bool = False,
		mirror: str | None = None) -> str:
	"""A System message in ``thread`` by ``author``, pointing at each (type, name) of ``targets``: a root card or a room
	mirror (``mirror``: the reply it mirrors). It is never rate-counted and tells no one by a notice. ``quiet``: the
	migration's cards, whose live events and counter jobs are held back too; ``creation`` dates such a card (Frappe
	stamps its own on insert)."""
	doc = frappe.get_doc({"doctype": "Discuss Message", "thread": thread, "content": SYSTEM_TEXT})
	frappe.flags[SYSTEM] = frappe._dict(thread=thread, author=author, quiet=quiet, mirror=mirror, consumed=False)
	try:
		# ignore_permissions: the server's message, by the author it names, with no membership read (§14.2).
		doc.insert(ignore_permissions=True)
	finally:
		frappe.flags[SYSTEM] = None
	for target_type, target_name in targets:
		pointer.add(doc, target_type, target_name)
	if creation:
		frappe.db.set_value("Discuss Message", doc.name, {"creation": creation, "modified": creation},
			update_modified=False)
	return doc.name


def take_system(doc):
	"""Called by DiscussMessage.before_insert: the System flag, consumed, when it is this insert's; else None."""
	flag = frappe.flags.get(SYSTEM)
	if not flag or flag.consumed or flag.thread != doc.thread:
		return None
	flag.consumed = True
	return flag


def claim_parts(doc, thread, claim) -> str:
	"""Run each claimed part's own check, after the core checks, and return the kind the message carries. A part not
	declared for this audience or sender is refused before its claim, so a new audience fails closed."""
	ctx = SendCtx(thread=thread, author=doc.author, sender=sender_of(doc.author), staff_only=bool(doc.staff_only))
	known = parts.by_key()
	kinds = {"Files"} if doc.file else set()
	doc.flags.cc_parts = {}
	for key, value in ((claim.parts or {}) if claim else {}).items():
		part = known.get(key)
		if not part or part.claim is None or thread.audience not in part.audiences or ctx.sender not in part.senders:
			frappe.throw(_("This message has a part that cannot be sent: {0}").format(key), frappe.PermissionError)
		doc.flags.cc_parts[key] = part.claim(ctx, value)
		if part.implies_kind:
			kinds.add(part.implies_kind)
	return derive_kind(kinds)


def write_parts(doc) -> None:
	"""Called by DiscussMessage.after_insert: each claimed part's own rows, under the claim the insert consumed (P3-65,
	§13.3 Part.write). A write that raises takes the message back with it: the request rolls back whole."""
	known = parts.by_key()
	for key, value in (doc.flags.get("cc_parts") or {}).items():
		part = known.get(key)
		if part and part.write:
			part.write(doc, value)


def rate_limit(user: str) -> None:
	"""Count one message of ``user`` (DiscussMessage.before_insert). The count and its expiry are kept together, as
	client_files.check_burst does. System Managers, patches, migrations and installs are not counted."""
	if _unlimited(user):
		return
	key = _rate_key(user)
	sent = frappe.cache.incrby(key, 1)
	if sent == 1 or frappe.cache.ttl(key) == -1:
		frappe.cache.expire(key, RATE_WINDOW)
	if sent > RATES[sender_of(user)]:
		_refuse_rate()


def check_rate(user: str) -> None:
	"""Refuse when ``user`` has no message left in this minute, without counting: a client's chat upload asks before its
	scan (attachments.upload, P3-65)."""
	if _unlimited(user):
		return
	sent = cint(frappe.safe_decode(frappe.cache.get(_rate_key(user)) or b"0"))
	if sent >= RATES[sender_of(user)]:
		_refuse_rate()


def queue_counters(thread: str, message: str) -> None:
	"""S8 (F13): the thread row's counters move in a short job after the commit, never inside the message request,
	where a write to the shared thread row lost to any other post with MariaDB 1020 (D-177). The job is queued only
	after the commit, so a queue that is down or full costs the counters, never the message or its event."""
	frappe.db.after_commit.add(partial(_queue_counters, thread, message))


def _queue_counters(thread: str, message: str) -> None:
	if frappe.in_test:
		# In-process under the test runner: a worker would write the row under the tests' own open transactions,
		# which then fail with 1020 (measured in P3-63's first full run).
		update_counters(thread, message)
		return
	try:
		# One job per message: a deduplicated job already running would miss a message committed after its snapshot.
		frappe.enqueue("construction_core.discuss.send.update_counters", queue="short", thread=thread, message=message)
	except Exception:
		frappe.logger("construction_core").exception("The chat thread counters were not queued")


def update_counters(thread: str, message: str | None = None) -> None:
	"""Count and date the messages a client of the thread may read: no staff-only notes, as clients read these
	fields, no removed messages (S8, P3-68), and no System cards or mirrors, as unread leaves them out (§14.5). A lost 1020 race is tried once more on a fresh snapshot. Then the thread's readers are told, after the
	commit and by ids, so their lists show the new counters."""
	try:
		_write_counters(thread)
	except frappe.QueryDeadlockError:
		frappe.db.rollback()  # the job wrote nothing else; the worker commits after the job returns
		_write_counters(thread)
	if message and frappe.db.exists("Discuss Message", message):
		from construction_core.discuss import live

		live.message_changed(frappe.get_doc("Discuss Message", message))


def _write_counters(thread: str) -> None:
	if not frappe.db.exists("Discuss Thread", thread):
		return
	row = frappe.db.sql("""select count(*), max(creation) from `tabDiscuss Message`
		where thread = %s and ifnull(staff_only, 0) = 0 and ifnull(kind, '') != 'System' and ifnull(removed, 0) = 0""",
		thread)[0]
	frappe.db.set_value("Discuss Thread", thread, {"message_count": row[0] or 0, "last_message_on": row[1]},
		update_modified=False)


def _thread(thread, sender: str):
	if not isinstance(thread, str) or not thread:
		frappe.throw(_("Choose a conversation"))
	t = frappe.get_doc("Discuss Thread", thread)
	if sender == "client":
		checks.client_send(t)
	else:
		t.check_permission("read")
	return t


def _first(user: str, client_id: str | None, thread: str) -> str | None:
	"""The message this sender already made with this id: a retry returns it. An id used in another thread is
	refused, never answered with that thread's message."""
	if not client_id:
		return None
	row = frappe.db.get_value("Discuss Message", {"author": user, "client_id": client_id}, ["name", "thread"],
		as_dict=True)
	if row and row.thread != thread:
		frappe.throw(_("This send has an invalid id"))
	return row.name if row else None


def _insert(t, user, sender, text, client_id, staff_only, claimed, file, counted) -> str:
	doc = frappe.get_doc({"doctype": "Discuss Message", "thread": t.name, "content": text, "staff_only": staff_only,
		"client_id": client_id, "file": file})
	point = "cc_send_" + frappe.generate_hash(length=8)
	messages = len(frappe.local.message_log)
	frappe.db.savepoint(point)
	frappe.flags[CLAIM] = frappe._dict(thread=t.name, author=user, client_id=client_id, parts=claimed, consumed=False,
		uncounted=not counted)
	try:
		# ignore_permissions for a client only: the claim is their create (D-387), and before_insert still reads
		# the thread as them. Staff keep their role's create and Frappe's own checks.
		doc.insert(ignore_permissions=sender == "client")
	except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
		if not client_id:
			raise
		# The same send won in another request (1062). Its row was committed after this request's snapshot began, so
		# only a new snapshot sees it: without a file this request wrote nothing before the insert, so it is taken back
		# whole. A file send keeps its stored file and rolls back to the savepoint only.
		del frappe.local.message_log[messages:]  # Frappe's "must be unique" message is not this answer
		if file:
			frappe.db.rollback(save_point=point)
		else:
			frappe.db.rollback()
		return _first(user, client_id, t.name) or _raise_again()
	except frappe.QueryDeadlockError:
		if not client_id or file:
			raise
		# 1020 rolled the whole transaction back. Without a file this request wrote nothing before the insert (send_file
		# stores its file first and keeps its own retry), so start a new snapshot and read the winner.
		frappe.db.rollback()
		return _first(user, client_id, t.name) or _raise_again()
	finally:
		frappe.flags[CLAIM] = None
	frappe.db.release_savepoint(point)
	frappe.flags.setdefault(checks.SENT, []).append(doc.name)  # the replies this request made (a mirror names one)
	return doc.name


def _raise_again():
	frappe.throw(_("This message could not be sent just now. Please try again."))


def _unlimited(user: str) -> bool:
	return bool(_bypass(user) or frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install)


def _rate_key(user: str) -> str:
	return frappe.cache.make_key(f"cc:discuss:send:{user}")


def _refuse_rate():
	frappe.throw(_("You have sent many messages in a short time. Wait a minute and try again."),
		frappe.RateLimitExceededError)
