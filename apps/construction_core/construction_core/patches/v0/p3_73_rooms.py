"""P3-73 (D-413, D-418, design §14.3): every project gets its rooms, every other conversation moves into one as a thread,
and each thread gets its root card. Safe to re-run: each step skips what is done already.

1. Rooms, per project and audience: the oldest Open conversation on the project itself takes the room's key (QR-1),
   so its name, links, read states, pins and bell notices stay on the room; else a new room is made.
2. Every other thread of the project, record threads and Locked or Resolved ones the same, gets ``in_room`` by
   db.set_value: the controller's anchor read fails for a record that is gone.
3. Root cards: one per thread whose Discuss Anchor has no ``message_id`` yet, by the thread's owner and dated at the
   thread's own creation, never at its first message: in a Client thread that can be a staff-only note, and its time
   would tell the client that hidden activity exists (the D-412 class). Bell notices, live events and counter jobs are
   held back; the counters then run once per room.
4. A missing Discuss Anchor row is made, and ``message_id`` is backfilled.

Closed projects are migrated the same (P3-59's refusal is unchanged). No read state is seeded (§14.5).
"""

import frappe

from construction_core.discuss import rooms
from construction_core.discuss.send import _write_counters
from construction_core.providers.chat import AUDIENCES

THREAD = ("name", "project", "audience", "anchor_doctype", "anchor_name", "in_room", "owner", "creation")


def execute():
	for project in frappe.get_all("Construction Project", order_by="creation asc", pluck="name"):
		migrate(project, commit=True)


def migrate(project: str, commit: bool = False) -> None:
	"""``commit``: each room is got in a transaction of its own, so one lost to a race is read again after a full
	rollback that takes back nothing else; the project's threads are then committed together."""
	homes = {}
	for audience in AUDIENCES:
		homes[audience] = _room(project, audience, commit)
		if commit:
			frappe.db.commit()
	threads = frappe.get_all("Discuss Thread", filters={"project": project, "room_key": ["is", "not set"]},
		fields=list(THREAD), order_by="creation asc, name asc")
	for t in threads:
		if t.audience not in homes:
			continue
		if not t.in_room:
			t.in_room = homes[t.audience]
			frappe.db.set_value("Discuss Thread", t.name, "in_room", t.in_room, update_modified=False)
		anchor = _anchor(t)
		if not frappe.db.get_value("Discuss Anchor", anchor, "message_id"):
			author = t.owner if frappe.db.exists("User", t.owner) else "Administrator"  # an owner may be gone
			card = rooms.card(t, author, creation=t.creation, quiet=True)
			frappe.db.set_value("Discuss Anchor", anchor, "message_id", card, update_modified=False)
	if commit:
		frappe.db.commit()  # the project's work is kept before its counters, which may lose a race
	for home in homes.values():
		# Not update_counters, which takes a lost race (1020) back whole and tries once more: here the error stops the
		# patch, so it is never marked done with a project's work rolled back.
		_write_counters(home)
	if commit:
		frappe.db.commit()


def _room(project: str, audience: str, own_transaction: bool) -> str:
	key = rooms.key(project, audience)
	found = frappe.db.get_value("Discuss Thread", {"room_key": key})
	if found:
		return found
	oldest = frappe.get_all("Discuss Thread", filters={"project": project, "audience": audience,
		"anchor_doctype": "Construction Project", "anchor_name": project, "status": "Open",
		"in_room": ["is", "not set"]}, order_by="creation asc, name asc", limit=1, pluck="name")
	if oldest:
		frappe.db.set_value("Discuss Thread", oldest[0], "room_key", key, update_modified=False)
		return oldest[0]
	return rooms.room(project, audience, own_transaction)


def _anchor(t) -> str:
	found = frappe.db.get_value("Discuss Anchor", {"thread_id": t.name})
	if found:
		return found
	# ignore_permissions: the anchor row is the system's index of threads, as DiscussThread.after_insert makes it;
	# ignore_links: its record or its author may be gone.
	return frappe.get_doc({"doctype": "Discuss Anchor", "project": t.project, "anchor_doctype": t.anchor_doctype,
		"anchor_name": t.anchor_name, "provider": "discuss", "thread_id": t.name, "audience": t.audience,
		"created_by": t.owner}).insert(ignore_permissions=True, ignore_links=True).name
