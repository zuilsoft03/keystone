"""The staff notification bell's core (P3-06; D-139, D-160, D-175, DR-5, DR-6, DR-8).

A notice is a Notification Log row of type Alert, which is never emailed (``notification_skip_email_types``), written
only for enabled staff who may read its record and allow notices. It keeps what happened, never what was said: the
kind, the record, the actor and the from->to state, captured in the request that saved the record, in ``email_header``
as a versioned key (``cc1|kind|from|to``). The words are built when the bell is read, in the reader's view, by the shell
(rule 3d). Notification Log announces nothing beyond its reader's own room (overrides.realtime.OwnRoomOnly).

A client gets no notice row: an @mention mails them a link that opens the conversation in the portal, without the
message (D-160). When the team writes in a Client conversation, its clients get one activity email per conversation
until they open it, with no text (P3-69, D-371).
"""

import html
import re
from functools import partial
from urllib.parse import quote, urlencode

import frappe
from frappe import _
from frappe.desk.doctype.notification_settings.notification_settings import (
	is_email_notifications_enabled,
	is_email_notifications_enabled_for_type,
	is_notifications_enabled,
)
from frappe.utils import add_to_date, cint, escape_html, get_fullname, get_url, now_datetime, strip_html

from construction_core.onboarding.mail import _brand_args, credit_html
from construction_core.permissions import client_section_open, is_client

NOTICES_EVENT = "cc_notices"  # never "notification": Desk's bell adds one to its badge for each of those
KEY = "cc1"
TYPE = "Alert"
CLIENT_MESSAGE, MENTION, STATE, ASSIGNED, CLIENT_FILE = "client_message", "mention", "state", "assigned", "client_file"
CLIENT_JOINED, CLIENT_WAITING = "client_joined", "client_waiting"  # P3-16 (D-209): about the project itself
REPLY = "reply"  # P3-69 (design §3.9): a reply in a thread the reader follows
# P3-71 (design §3.10, D-380): a file request's files arrived (to its requester, once per request until read), one was
# asked for again (to a staff uploader) and a reminder (to a staff recipient)
FILES_RECEIVED, FILES_ASKED_AGAIN, FILES_REMINDER = "files_received", "files_asked_again", "files_reminder"
# P3-78 (approvals §3.6, §3.7): to the project's managers, an answer's receipt not sent yet, and "This was not me"
RECEIPT_FAILED, APPROVAL_DISPUTED = "receipt_failed", "approval_disputed"
# P3-78 (approvals §3.10, §3.13): "Client answered" (one kind per answer, for its own words) to the requester and the
# managers; a final record changed after its approval, to the managers; a request overdue, to its requester
CLIENT_APPROVED, CLIENT_RETURNED = "client_approved", "client_returned"
APPROVAL_CHANGED, APPROVAL_OVERDUE = "approval_changed", "approval_overdue"
# P3-82 (approvals §14.2, §14.3): an internal step waits on its people (sent, nudged or next), a step returned to the
# sender, a step past its due time (its people and the sender), and a route changed (every Construction Manager)
STEP_WAITING, STEP_RETURNED, STEP_OVERDUE = "approval_step", "approval_step_returned", "approval_step_overdue"
ROUTE_CHANGED = "approval_route_changed"
GROUPED = (CLIENT_MESSAGE, REPLY)  # the bell shows these once per (kind, conversation) until read
KIND_DOCTYPES = {
	CLIENT_MESSAGE: {"Discuss Thread"},
	MENTION: {"Discuss Thread"},
	REPLY: {"Discuss Thread"},
	FILES_RECEIVED: {"File Request"},
	FILES_ASKED_AGAIN: {"File Request"},
	FILES_REMINDER: {"File Request"},
	STATE: {"RFI", "Submittal", "Variation Order", "Project Document"},
	ASSIGNED: {"RFI", "Submittal", "Project Document"},
	CLIENT_FILE: {"File"},
	CLIENT_JOINED: {"Construction Project"},
	CLIENT_WAITING: {"Construction Project"},
	RECEIPT_FAILED: {"Approval Request"},
	APPROVAL_DISPUTED: {"Approval Request"},
	CLIENT_APPROVED: {"Approval Request"},
	CLIENT_RETURNED: {"Approval Request"},
	APPROVAL_CHANGED: {"Approval Request"},
	APPROVAL_OVERDUE: {"Approval Request"},
	STEP_WAITING: {"Approval Request"},
	STEP_RETURNED: {"Approval Request"},
	STEP_OVERDUE: {"Approval Request"},
	ROUTE_CHANGED: {"Approval Route"},
}
STATE_FIELD = {"RFI": "status", "Submittal": "status", "Variation Order": "stage", "Project Document": "status"}
APPROVERS = "approve_variation"  # in TOLD: the staff who may approve a variation
# Who is told when a record moves into a state (D-175). Fields name users on the record; APPROVERS is computed.
TOLD = {
	("RFI", "Issued"): ("assigned_to",),
	("RFI", "Answered"): ("raised_by",),
	("RFI", "Closed"): ("assigned_to", "answered_by"),
	("Submittal", "Submitted"): ("reviewer",),
	("Submittal", "Approved"): ("owner",),
	("Submittal", "Approved as Noted"): ("owner",),
	("Submittal", "Revise and Resubmit"): ("owner",),
	("Submittal", "Rejected"): ("owner",),
	("Variation Order", "Change Order Request"): (APPROVERS,),
	("Variation Order", "Approved Change"): ("owner",),
	("Variation Order", "Rejected"): ("owner",),
	("Variation Order", "Potential Change"): ("owner",),
	("Project Document", "Lead Review"): ("lead_reviewer",),
	("Project Document", "Coordination Review"): ("lead_reviewer",),
	("Project Document", "Client Review"): ("author", "lead_reviewer"),
	("Project Document", "Published"): ("author", "lead_reviewer"),
	("Project Document", "WIP"): ("author",),
}
# A person a record waits on: a new one is told while it waits (an "assigned" notice).
WAITS_ON = {
	"RFI": ("assigned_to", {"Issued"}),
	"Submittal": ("reviewer", {"Submitted", "Under Review"}),
	"Project Document": ("lead_reviewer", {"Lead Review", "Coordination Review"}),
}
ERROR_TITLE = "construction_core notice failed"
# P3-69 (D-371): the activity email's sign-in link per room audience. P3-32 adds the partner room's /partner/login
# link here (D-444); an audience without a link gets no email.
ACTIVITY_LINKS = {"Client": lambda project, thread: portal_link(project, thread)}
ACTIVITY_LIMITS = {"address_per_day": 10}  # as the join codes' address cap (onboarding.join.LIMITS)
ACTIVITY_REF = "Discuss Thread"  # the Email Queue rows name their conversation: "mailed since opened" and the cap
FIELDS = ["name", "creation", "read", "type", "from_user", "document_type", "document_name", "email_header"]


def key(kind: str, from_state: str | None = None, to_state: str | None = None) -> str:
	if kind not in KIND_DOCTYPES:
		raise ValueError(f"unknown notice kind {kind!r}")
	return "|".join([KEY, kind, from_state or "", to_state or ""])


def parse(row) -> frappe._dict | None:
	"""A stored row as a notice, or None for any row this module did not write."""
	parts = (row.get("email_header") or "").split("|")
	if row.get("type", TYPE) != TYPE or len(parts) != 4 or parts[0] != KEY:
		return None
	kind = parts[1]
	if row.get("document_type") not in KIND_DOCTYPES.get(kind, ()):
		return None
	return frappe._dict(id=row.get("name"), kind=kind, doctype=row.get("document_type"), docname=row.get("document_name"),
		actor=row.get("from_user"), from_state=parts[2] or None, to_state=parts[3] or None, read=bool(row.get("read")),
		creation=row.get("creation"))


def _plain(value) -> str:
	"""Text that cannot render as markup anywhere a stored line is shown (Desk's bell renders it as HTML)."""
	return re.sub("[<>]", "", html.unescape(strip_html(str(value or ""))))[:140]


def _desk_line(kind, doc, actor, from_state, to_state) -> str:
	"""Desk's bell line: industry words (Desk keeps them, D-155), no record title, no message (D-175)."""
	who = _plain(get_fullname(actor))
	if kind == CLIENT_MESSAGE:
		return _("{0} wrote in a client conversation").format(who)
	if kind == MENTION:
		return _("{0} mentioned you").format(who)
	if kind == REPLY:
		return _("{0} replied in a thread you follow").format(who)
	if kind == STATE:
		return _("{0} moved {1} {2} from {3} to {4}").format(who, _(doc.doctype), doc.name, from_state, to_state)
	if kind == ASSIGNED:
		return _("{0} passed {1} {2} to you").format(who, _(doc.doctype), doc.name)
	if kind == CLIENT_JOINED:
		return _("{0} joined {1} as a client contact").format(who, doc.name)
	if kind == CLIENT_WAITING:
		return _("A new client contact is waiting for you in {0}").format(doc.name)
	if kind == FILES_RECEIVED:
		return _("{0} sent files you asked for").format(who)
	if kind == FILES_ASKED_AGAIN:
		return _("{0} asked you again for a file").format(who)
	if kind == FILES_REMINDER:
		return _("{0} is waiting for files from you").format(who)
	if kind == RECEIPT_FAILED:
		return _("The receipt for an approval of {0} could not be sent yet").format(doc.subject_name)
	if kind == APPROVAL_DISPUTED:
		return _("{0} said an approval of {1} was not them").format(who, doc.subject_name)
	if kind == CLIENT_APPROVED:
		return _("{0} approved {1}").format(who, doc.subject_name)
	if kind == CLIENT_RETURNED:
		return _("{0} returned {1} with a reason").format(who, doc.subject_name)
	if kind == APPROVAL_CHANGED:
		return _("{0} changed after the client approved it").format(doc.subject_name)
	if kind == APPROVAL_OVERDUE:
		return _("The client approval of {0} is overdue").format(doc.subject_name)
	if kind == STEP_WAITING:
		return _("An internal approval step of {0} waits on you").format(doc.subject_name)
	if kind == STEP_RETURNED:
		return _("{0} returned {1} at an internal step").format(who, doc.subject_name)
	if kind == STEP_OVERDUE:
		return _("An internal approval step of {0} is overdue").format(doc.subject_name)
	if kind == ROUTE_CHANGED:
		return _("{0} changed the approval steps for {1}").format(who, _(doc.name))
	return _("{0} sent a file").format(who)


def eligible(user, doc, actor) -> bool:
	"""An enabled System User other than the actor, with notices on, who may read the record (DR-6)."""
	if not user or user in ("Guest", actor):
		return False
	row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
	if not row or not row.enabled or row.user_type != "System User":
		return False
	if not is_notifications_enabled(user):  # a direct insert skips Frappe's own filter (notification_log.py)
		return False
	return bool(frappe.has_permission(doc.doctype, "read", doc=doc, user=user, throw=False))


def notify(users, kind, doc, *, actor=None, from_state=None, to_state=None, source=None, coalesce=False) -> list[str]:
	"""Write one notice per eligible user; return the users written for. A failure to write one never fails the save
	that caused it (it is logged), except a deadlock or a timeout, after which the transaction is gone."""
	if doc.doctype not in KIND_DOCTYPES.get(kind, ()):
		raise ValueError(f"a {kind} notice is not about a {doc.doctype}")
	if kind == STATE:
		options = (frappe.get_meta(doc.doctype).get_field(STATE_FIELD[doc.doctype]).options or "").split("\n")
		if from_state not in options or to_state not in options:
			raise ValueError("a state notice names two states of its record")
	elif from_state:
		raise ValueError(f"a {kind} notice has no from-state")
	actor = actor or frappe.session.user
	header = key(kind, from_state, to_state)
	written = []
	for user in dict.fromkeys(users or ()):
		if not eligible(user, doc, actor):
			continue
		if coalesce and frappe.db.exists("Notification Log", {"for_user": user, "read": 0, "type": TYPE,
				"document_type": doc.doctype, "document_name": doc.name, "email_header": header}):
			continue  # once per conversation until it is opened
		if _insert({"doctype": "Notification Log", "type": TYPE, "for_user": user, "from_user": actor,
				"document_type": doc.doctype, "document_name": doc.name, "email_header": header,
				"source_doctype": source and source.doctype, "source_name": source and source.name,
				"subject": _plain(_desk_line(kind, doc, actor, from_state, to_state))}, doc):
			written.append(user)
	return written


def _insert(row, doc) -> bool:
	point = "cc_notice_" + frappe.generate_hash(length=8)
	frappe.db.savepoint(point)
	try:
		frappe.get_doc(row).insert(ignore_permissions=True)  # the reader's own notice, written by the server (DR-5)
	except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
		raise
	except Exception:
		frappe.db.rollback(save_point=point)
		frappe.log_error(title=ERROR_TITLE, reference_doctype=doc.doctype, reference_name=doc.name)
		return False
	frappe.db.release_savepoint(point)
	return True


def _approvers(doc) -> list[str]:
	from construction_core.discuss.api import staff_members

	return [u for u in staff_members(doc.project)
		if frappe.has_permission(doc.doctype, APPROVERS, doc=doc, user=u, throw=False)]


def on_record_update(doc, method=None):
	"""doc_events on_update of RFI, Submittal, Variation Order and Project Document: the from->to state and the actor
	are those of this save, read here, in the saving request (never later from the record's current state)."""
	if frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install:
		return
	before = doc.get_doc_before_save()
	if not before:
		return  # an insert starts in its first state; nothing has moved
	field = STATE_FIELD[doc.doctype]
	old, new = before.get(field), doc.get(field)
	plan = {}
	if old != new:
		for who in TOLD.get((doc.doctype, new), ()):
			for user in (_approvers(doc) if who == APPROVERS else [doc.get(who)]):
				if user:
					plan.setdefault(user, (STATE, old, new))
	if doc.doctype in WAITS_ON:
		person_field, waiting = WAITS_ON[doc.doctype]
		person = doc.get(person_field)
		if new in waiting and person and person != before.get(person_field):
			plan.setdefault(person, (ASSIGNED, None, new))  # the state notice wins: one notice per person per save
	groups = {}
	for user, (kind, from_state, to_state) in plan.items():
		groups.setdefault((kind, from_state, to_state), []).append(user)
	for (kind, from_state, to_state), users in groups.items():
		notify(users, kind, doc, from_state=from_state, to_state=to_state)


def on_message(message):
	"""Discuss Message after_insert: staff @mentions get a notice, clients an email; a client's message tells the
	project's team once per conversation until they open it; a reply in a thread tells its staff followers the same way.
	One notice per person per message: a mention, else a client message, else a reply. The team's message in a Client
	conversation queues the clients' activity email (after the commit)."""
	from construction_core.discuss.api import staff_members

	thread = frappe.get_doc("Discuss Thread", message.thread)
	mentioned = [u for u in (message.mentions or "").split("\n") if u and u != message.author]
	staff = [u for u in mentioned if not is_client(u)]
	notify(staff, MENTION, thread, actor=message.author, source=message)
	told = {message.author, *staff}
	for client in mentioned:
		if is_client(client):
			mail_client_mention(client, message, thread)
	if is_client(message.author) and message.audience == "Client" and not message.staff_only:
		team = [u for u in staff_members(message.project) if u not in told]
		notify(team, CLIENT_MESSAGE, thread, actor=message.author, source=message, coalesce=True)
		told.update(team)
	if thread.in_room:  # a thread, not a room's own timeline (§14.5)
		notify([u for u in _followers(thread.name) if u not in told], REPLY, thread, actor=message.author,
			source=message, coalesce=True)
	queue_activity(message, skip=[u for u in mentioned if is_client(u)])


def _followers(thread: str) -> list[str]:
	"""Who follows the thread (§14.5), and the root message's author, whose follow row is written only after the
	first reply's commit: the first reply tells them too ("someone replied to your message", §3.9)."""
	root = frappe.db.get_value("Discuss Anchor", {"thread_id": thread}, "message_id")
	author = root and frappe.db.get_value("Discuss Message", root, "author")
	return list(dict.fromkeys([*([author] if author else []),
		*frappe.get_all("Discuss Follow", filters={"thread": thread}, pluck="user")]))


def notices_of(user, *, unread_only=False, skip_doctypes=(), start=0, page_length=50) -> list:
	"""The user's own notices written here, newest first, parsed. Not whitelisted: the caller checks who asks."""
	filters = {"for_user": user, "type": TYPE, "email_header": ["like", f"{KEY}|%"]}
	if unread_only:
		filters["read"] = 0
	if skip_doctypes:
		filters["document_type"] = ["not in", list(skip_doctypes)]
	rows = frappe.get_all("Notification Log", filters=filters, fields=FIELDS, order_by="creation desc",
		start=start, page_length=page_length)
	return [n for n in (parse(r) for r in rows) if n]


def _set_read(user, names) -> list[str]:
	if names:
		frappe.db.set_value("Notification Log", {"name": ["in", names], "for_user": user}, "read", 1, update_modified=False)
		frappe.publish_realtime(NOTICES_EVENT, {}, user=user, after_commit=True)
	return names


def _unread(user, **filters) -> list[str]:
	return frappe.get_all("Notification Log", filters={"for_user": user, "read": 0, "type": TYPE,
		"email_header": ["like", f"{KEY}|%"], **filters}, pluck="name")


def mark_notice_read(user, name) -> list[str]:
	"""One of the user's notices; a grouped one (the bell shows it once per conversation) with the unread notices of
	its own kind in that conversation, and no other kind."""
	row = frappe.db.get_value("Notification Log", {"name": name, "for_user": user},
		["document_type", "document_name", "email_header", "type", "read"], as_dict=True)
	notice = row and parse(row)
	if not notice:
		return []
	names = _unread(user, name=name)
	if notice.kind in GROUPED and not row.read:  # a read row sweeps nothing: its newer siblings are a new item
		names = list(dict.fromkeys(names + _unread(user, document_type="Discuss Thread", document_name=row.document_name,
			email_header=key(notice.kind))))
	return _set_read(user, names)


def mark_all_notices_read(user, skip_doctypes=()) -> list[str]:
	filters = {"document_type": ["not in", list(skip_doctypes)]} if skip_doctypes else {}
	return _set_read(user, _unread(user, **filters))


def clear_thread(user, thread) -> list[str]:
	"""Opening a conversation clears the reader's notices about it."""
	return _set_read(user, _unread(user, document_type="Discuss Thread", document_name=thread))


def portal_link(project, thread) -> str:
	"""The portal conversation, through the sign-in page so a signed-out client lands there after signing in."""
	target = f"/portal/{quote(project, safe='')}?" + urlencode({"tab": "discuss", "thread": thread})
	return get_url("/portal/login?redirect-to=" + quote(target, safe=""))  # the clients' sign-in (D-265)


def _can_mail() -> bool:
	return bool(frappe.db.exists("Email Account", {"enable_outgoing": 1}))


def mail_client_mention(client, message, thread) -> bool:
	"""The client's @mention email (D-160): who mentioned them and in which project, a link to the conversation in the
	portal, and nothing they said. Only when the client may open that conversation and allows mention emails."""
	if not (frappe.db.get_value("User", client, "enabled") and is_client(client)
			and frappe.has_permission("Discuss Thread", "read", doc=thread, user=client, throw=False)
			and is_notifications_enabled(client) and is_email_notifications_enabled_for_type(client, "Mention")
			and _can_mail()):
		return False
	project_name = frappe.db.get_value("Construction Project", thread.project, "project_name") or thread.project
	subject = _("{0} mentioned you in {1}").format(_plain(get_fullname(message.author)), _plain(project_name))
	link = portal_link(thread.project, thread.name)
	body = (f"<p>{escape_html(subject)}</p>"
		f'<p><a href="{escape_html(link)}">{escape_html(_("Open the conversation"))}</a></p>') + credit_html()  # D-402
	try:
		# No `header`: Frappe's masthead would read its own app name from Website Settings, not the firm's or ours.
		frappe.sendmail(recipients=[frappe.db.get_value("User", client, "email") or client], subject=subject,
			message=body, now=frappe.in_test)
	except frappe.OutgoingEmailError:
		frappe.log_error(title=ERROR_TITLE, reference_doctype="Discuss Thread", reference_name=thread.name)
		return False
	return True


# --- the clients' activity email (P3-69, D-371) ------------------------------------------------------------------


def queue_activity(message, skip=()) -> None:
	"""The team wrote in a Client conversation, not as a staff-only note: the activity email is worked out after the
	commit. ``skip``: the clients this message mentions (they get the mention email only)."""
	if message.staff_only or message.audience not in ACTIVITY_LINKS or is_client(message.author):
		return
	frappe.db.after_commit.add(partial(_queue_activity, message.name, list(skip)))


def _queue_activity(message: str, skip: list) -> None:
	if frappe.in_test:
		mail_activity(message, skip)  # in-process under the test runner, as rooms._queue_follows does
		return
	try:
		frappe.enqueue("construction_core.notifications.mail_activity", queue="short", message=message, skip=skip)
	except Exception:
		frappe.logger("construction_core").exception("The clients' activity email was not queued")


def mail_activity(message: str, skip=()) -> list[str]:
	"""The job: one email to each client of the conversation who may open it now and allows email, unless they were
	mailed about it since they last opened it, or reached the day's cap. The message is read again: a removed one, a
	staff-only note or a System card mails no one. Returns the clients mailed."""
	from construction_core.discuss.live import client_members

	m = frappe.db.get_value("Discuss Message", message, ["name", "thread", "project", "audience", "author",
		"staff_only", "removed", "kind"], as_dict=True)
	if not m or m.removed or m.staff_only or m.kind == "System" or m.audience not in ACTIVITY_LINKS:
		return []
	if is_client(m.author) or not (_can_mail() and client_section_open("Discuss Message", m.project)):
		return []
	thread = frappe.get_doc("Discuss Thread", m.thread)
	return [c for c in client_members(m.project)  # none while the portal is off
		if c not in skip and c != m.author and _mail_activity_to(c, m, thread)]


def _mail_activity_to(client: str, m, thread) -> bool:
	user = frappe.db.get_value("User", client, ["enabled", "email"], as_dict=True)
	if not (user and user.enabled and is_client(client)
			and frappe.has_permission("Discuss Thread", "read", doc=thread, user=client, throw=False)
			and is_notifications_enabled(client) and is_email_notifications_enabled(client)):
		return False
	email = user.email or client
	opened = frappe.db.get_value("Discuss Read State", {"thread": thread.name, "user": client}, "last_read_on")
	if _mailed_since(thread.name, email, opened) or _mailed_today(email) >= _activity_cap():
		return False
	# Two jobs at once (two sends): the first takes this key, for this conversation and this last opening only.
	if not frappe.cache.set(frappe.cache.make_key(f"cc:activity:{thread.name}:{client}:{opened}"), 1, nx=True, ex=120):
		return False
	project = _plain(frappe.db.get_value("Construction Project", m.project, "project_name") or m.project)
	try:
		# now=False: Frappe's sender flushes the queue; the row stays as the record "mailed, not yet opened".
		frappe.sendmail(recipients=[email], subject=activity_subject(project), template="cc_chat_activity",
			args={**_brand_args(), "project": project, "link": ACTIVITY_LINKS[m.audience](m.project, thread.name)},
			reference_doctype=ACTIVITY_REF, reference_name=thread.name, add_unsubscribe_link=0, now=False)
	except frappe.OutgoingEmailError:
		frappe.log_error(title=ERROR_TITLE, reference_doctype="Discuss Thread", reference_name=thread.name)
		return False
	return True


def activity_subject(project: str) -> str:
	"""No message text, no file name, no record title: who wrote (the team) and in which project (D-371). The firm
	leads once its name is set (D-401)."""
	from construction_core.onboarding.mail import brand

	if brand():
		return _("The team at {0} wrote to you in {1}").format(brand(), project)
	return _("The project team wrote to you in {0}").format(project)


def _activity_cap() -> int:
	return cint({**ACTIVITY_LIMITS, **(frappe.conf.get("cc_activity_limits") or {})}["address_per_day"])


def _mailed_since(thread: str, email: str, opened) -> bool:
	"""An activity email about ``thread`` went to ``email`` after the client last opened it (ever, if never)."""
	return bool(_activity_rows(email, "and q.reference_name = %(thread)s"
		+ (" and q.creation > %(opened)s" if opened else ""), thread=thread, opened=opened, limit=1))


def _mailed_today(email: str) -> int:
	return len(_activity_rows(email, "and q.creation > %(since)s", since=add_to_date(now_datetime(), days=-1)))


def _activity_rows(email: str, where: str, limit: int = 1000, **values) -> tuple:
	return frappe.db.sql(f"""select distinct q.name from `tabEmail Queue` q
		join `tabEmail Queue Recipient` r on r.parent = q.name
		where q.reference_doctype = %(ref)s and r.recipient = %(email)s {where} limit {cint(limit)}""",
		{"ref": ACTIVITY_REF, "email": email, **values})
