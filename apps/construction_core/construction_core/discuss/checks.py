"""The message checks, in one module (design rule 5, §13.1 S2). DiscussMessage.before_insert runs them for every insert,
so a staff REST insert and the provider path are checked too, not only our endpoints.

- The thread is read as the author: that re-checks membership, the portal, the section and the audience (rule 3).
- Nobody posts in a Locked thread or a closed project (P3-59); a client posts only in a Client thread and writes no
  staff-only note.
- Nobody writes a new staff-only note (D-419): "Discuss with team" replaces them. Only a patch makes one (legacy_note).
- A message has text, at most MAX_MESSAGE characters (F10: today's endpoints-only check moved here).
- ``client_id`` is the browser's id for one send: letters, digits, ``-`` and ``_``.
- The legacy ``file`` must be a file of this project, client visible in a Client thread, and readable by the author.
- ``@user@example.com`` mentions keep only the people the conversation's mention list offers; anyone else is dropped
  with no error (F6, P3-66). The ``@[u:n]`` and ``#[r:n]`` tokens are settled by their parts (DiscussMessage).
- A System message (the server's flag) is checked by ``system`` instead: it is the server's, not its author's.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint

from construction_core.discuss.registry import SYSTEM_TEXT
from construction_core.permissions import (
	client_portal_open,
	client_section_open,
	is_client,
	is_member,
	refuse_closed,
)

MAX_MESSAGE = 5000
SENT = "cc_discuss_sent"  # the messages this request made through send.send_impl, which a mirror may name
CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MENTION = re.compile(r"@([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def run(doc):
	"""Check one new message and set what the thread decides. Returns the thread."""
	thread = frappe.get_doc("Discuss Thread", doc.thread)
	thread.check_permission("read")
	doc.project, doc.audience = thread.project, thread.audience
	doc.author = frappe.session.user
	if thread.status == "Locked":
		frappe.throw(_("This thread is locked"))
	refuse_closed(thread.project)  # P3-59: a closed project takes no new message, from anyone
	if is_client(doc.author) and thread.audience != "Client":
		frappe.throw(_("You cannot post in this thread"), frappe.PermissionError)
	if doc.staff_only and is_client(doc.author):
		frappe.throw(_("Staff-only notes are for the project team"), frappe.PermissionError)
	if cint(doc.staff_only) and not legacy_note():  # a form's "0" is no note
		frappe.throw(_('Staff-only notes have stopped. Use "Discuss with team" on a client message to talk about it in '
			"the Team room."), frappe.PermissionError)
	doc.content = text(doc.content, empty=True)  # a Text message needs text: checked once the kind is known (P3-65)
	doc.client_id = client_id(doc.client_id)
	_check_file(doc)
	doc.mentions = "\n".join(_mentions(doc))
	return thread


def legacy_note() -> bool:
	"""A staff-only note is made only by a patch, a migration or an install (D-419, §14.2): never by a request, a
	System Manager's or a bypass user's included. Old notes keep D-098's guards; tests make them under the patch flag."""
	return bool(frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install)


def system(doc, flag):
	"""Check one System message under the server's flag (D-419) and return the thread. The thread decides project and
	audience, the flag the author, with no membership read (a migrated card's author may have left the project). It
	carries the one neutral text and nothing else: no note, id, file or mention."""
	thread = frappe.get_doc("Discuss Thread", doc.thread)
	if thread.status == "Locked":
		frappe.throw(_("This thread is locked"))
	if flag.get("mirror"):
		_check_mirror(thread, flag.mirror)
	doc.project, doc.audience, doc.author = thread.project, thread.audience, flag.author
	doc.content, doc.staff_only, doc.client_id, doc.file, doc.mentions = SYSTEM_TEXT, 0, None, None, ""
	return thread


def _check_mirror(room, reply: str) -> None:
	"""§14.4 row 4: a mirror names only the reply made in this request, in a thread of this room, with staff_only 0."""
	row = frappe.db.get_value("Discuss Message", reply, ["thread", "staff_only", "kind"], as_dict=True)
	if not (row and reply in (frappe.flags.get(SENT) or ()) and row.kind != "System" and not row.staff_only
			and room.room_key and frappe.db.get_value("Discuss Thread", row.thread, "in_room") == room.name):
		frappe.throw(_("Only a shared reply in a thread can also go to the room"), frappe.PermissionError)


def client_send(thread) -> None:
	"""A client's send (rule 3): the portal is on, the Discussion section is on, they are a member, it is a Client
	thread and it is open. A thread the client may not see answers as a refusal, never as its state."""
	user = frappe.session.user
	if not (is_member(user, thread.project) and client_portal_open(thread.project)
			and client_section_open("Discuss Message", thread.project)
			and frappe.has_permission("Discuss Thread", "read", doc=thread, throw=False)):
		frappe.throw(_("You cannot post in this thread"), frappe.PermissionError)
	if thread.audience != "Client":
		frappe.throw(_("You cannot post in this thread"), frappe.PermissionError)
	if thread.status == "Locked":
		frappe.throw(_("This thread is locked"))
	refuse_closed(thread.project)


def text(content, empty: bool = False) -> str:
	"""``empty``: the message carries files, so it may have no caption (P3-65): a file's name is never copied into the
	text (rule 2). DiscussMessage.before_insert still refuses a Text message without text."""
	content = (content or "").strip()
	if not content and not empty:
		frappe.throw(_("Write a message first"))
	if len(content) > MAX_MESSAGE:
		frappe.throw(_("A message is at most {0} characters").format(MAX_MESSAGE))
	return content


def client_id(value) -> str | None:
	"""None for no id: the unique (author, client_id) key never matches two NULLs, but it would match two ''."""
	if value in (None, ""):
		return None
	if not isinstance(value, str) or not CLIENT_ID.match(value):
		frappe.throw(_("This send has an invalid id"))
	return value


def _check_file(doc) -> None:
	if not doc.file:
		return
	f = frappe.db.get_value("File", doc.file, ["cc_project", "cc_client_visible"], as_dict=True)
	if not f or f.cc_project != doc.project:
		frappe.throw(_("The attachment must be a file of this project"))
	if doc.audience == "Client" and not doc.staff_only and not f.cc_client_visible:
		frappe.throw(_("In a client thread the attachment must be client visible"))
	frappe.get_doc("File", doc.file).check_permission("read")


def _mentions(doc) -> list[str]:
	"""Old ``@email`` text (FIT-20): the people the conversation's mention list offers (parts.mentions.audience).
	Anyone else is dropped with no error, so a send never tells who is a member (F6, P3-66)."""
	from construction_core.discuss.parts.mentions import audience

	emails = list(dict.fromkeys(m.lower() for m in MENTION.findall(doc.content or "")))
	if not emails:
		return []
	offered = {u.name.lower(): u.name for u in audience(doc.project, doc.audience, cint(doc.staff_only))}
	users = [offered.get(email) or offered.get((frappe.db.get_value("User", {"email": email}) or "").lower()) for email in emails]
	return list(dict.fromkeys(u for u in users if u))
