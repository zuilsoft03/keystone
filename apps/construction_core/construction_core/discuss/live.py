"""The chat's realtime router (design §13.1 S5, rule 8): the only chat module that publishes.

- ``readers(message)`` is the one routing function: the project's staff always, and each client of a Client message
  that is no staff-only note while the portal and the Discussion section are on. "Staff" means not a client until
  P3-27's is_staff (D-409).
- Every event goes to user rooms only, after the commit. No document or doctype room (D-394; clients join none, D-100).
- A payload carries ids only, and a key not listed for its event raises (typing keeps the name and picture it
  carries today, so the pages that show "… is typing" keep working).
- Message and change events name the ``room`` too (design §14.6): the thread itself for a room, else its room. A
  reply in a thread also tells its room that the root's reply line changed: CHANGED_EVENT {thread: the room, message:
  the root, part: "thread"}, to the reply's own readers, so a staff-only note tells no client.
"""

import frappe

from construction_core.permissions import client_portal_open, client_section_open, is_client

MESSAGE_EVENT = "cc_discuss_message"
CHANGED_EVENT = "cc_discuss_changed"  # a message's part changed: P3-65 and P3-68 publish it through message_changed
TYPING_EVENT = "cc_discuss_typing"
SEEN_EVENT = "cc_discuss_seen"
PIN_EVENT = "cc_discuss_pin"  # until P3-64 retires the Desk page (client_chat.js)
READ_EVENT = "cc_discuss_read"  # P3-74: the reader read a thread; their other tabs and devices drop its count
KEYS = {
	MESSAGE_EVENT: {"thread", "message", "author", "room"},
	CHANGED_EVENT: {"thread", "message", "part", "room"},
	TYPING_EVENT: {"thread", "user", "name", "image"},
	SEEN_EVENT: {"thread", "user"},
	PIN_EVENT: {"thread", "message", "pinned"},
	READ_EVENT: {"thread"},
}


def readers(message) -> list[str]:
	users = staff_members(message.project)
	if (message.audience == "Client" and not message.staff_only
			and client_section_open("Discuss Message", message.project)):
		users += client_members(message.project)
	return users


def message_event(message) -> None:
	users = readers(message)
	room = room_of(message.thread)
	publish(MESSAGE_EVENT, {"thread": message.thread, "message": message.name, "author": message.author,
		"room": room}, users)
	if room != message.thread:
		root = frappe.db.get_value("Discuss Anchor", {"thread_id": message.thread}, "message_id")
		if root:
			publish(CHANGED_EVENT, {"thread": room, "message": root, "part": "thread", "room": room}, users)


def message_changed(message, part: str | None = None) -> None:
	payload = {"thread": message.thread, "message": message.name, "room": room_of(message.thread)}
	if part:
		payload["part"] = part
	users = readers(message)
	if part == "approval" and not client_section_open("Approval Request", message.project):
		users = [u for u in users if not is_client(u)]  # the card's request has its own client rule (P3-78, T30)
	publish(CHANGED_EVENT, payload, users)


def room_of(thread: str) -> str:
	return frappe.db.get_value("Discuss Thread", thread, "in_room") or thread


def read_event(user: str, thread: str) -> None:
	"""Only to the reader's own user room (§14.6): no one else learns what they read."""
	publish(READ_EVENT, {"thread": thread}, [user])


def staff_event(project: str, event: str, payload: dict, exclude: str | None = None) -> None:
	"""Typing, seen and pins: staff information (D-098), never a client's."""
	publish(event, payload, [u for u in staff_members(project) if u != exclude])


def publish(event: str, payload: dict, users) -> None:
	if not set(payload) <= KEYS.get(event, set()):
		raise frappe.ValidationError(f"{event} cannot carry {sorted(set(payload) - KEYS.get(event, set()))}")
	for user in dict.fromkeys(users):
		frappe.publish_realtime(event, payload, user=user, after_commit=True)


def staff_members(project: str) -> list[str]:
	return [u for u in _members(project) if not is_client(u)]


def client_members(project: str) -> list[str]:
	"""The project's clients who may receive its events: none while its portal is off (P2-04 audit 5, D-117)."""
	if not client_portal_open(project):
		return []
	return [u for u in _members(project) if is_client(u)]


def _members(project: str) -> list[str]:
	users = frappe.get_all("Project Member", filters={"parenttype": "Construction Project", "parent": project},
		pluck="user")
	return [u for u in users if u]
