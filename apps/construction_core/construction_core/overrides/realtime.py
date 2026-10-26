"""DR-8 for Frappe's own updates: a project-scoped record announces changes in its own document room only.

Frappe's ``Document.notify_update`` also publishes ``list_update`` (the record name and the editing user) to the
``doctype:<DocType>`` room, which any user with read on the doctype may join, so a client of one project would
learn the names and editors of every project's records (D-029, P1-09). Desk list views of these doctypes then
refresh on navigation instead of live.
"""

from functools import partial

import frappe


class DocRoomOnly:
	def notify_update(self):
		if frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install:
			return
		frappe.publish_realtime(
			"doc_update",
			{"modified": self.modified, "doctype": self.doctype, "name": self.name},
			doctype=self.doctype,
			docname=self.name,
			after_commit=True,
		)


class OwnRoomOnly:
	"""Notification Log (P3-06, DR-8): a notice is announced only by its after_insert, the "notification" event in
	user:<for_user>. No doc_update (a shared row's room) and no list_update to doctype:Notification Log, which any
	staff user may join and which would name every notice and its actor. This covers every producer, Frappe's share,
	assignment and Desk mentions included.

	A core notice (construction_core.notifications) leaves Desk's "seen" flag to a short job after the commit (D-177).
	Frappe writes that one shared row per reader in the saving request, and two requests that notify the same person at
	once then fail the second save with MariaDB 1020 (snapshot isolation), measured on the dev stack. The job is queued
	only after the commit, so the notice never depends on the queue. A core notice is an Alert, which is never emailed,
	so nothing else of Frappe's after_insert applies to it."""

	def notify_update(self):
		return

	def after_insert(self):
		from construction_core.notifications import parse

		if not parse(self):
			return super().after_insert()
		frappe.publish_realtime("notification", after_commit=True, user=self.for_user)
		frappe.db.after_commit.add(partial(queue_unseen, self.for_user))


def queue_unseen(user: str):
	"""After the commit: queue Desk's dot (D-177). A queue that is down costs the dot only, never the saved notice."""
	try:
		frappe.enqueue("construction_core.overrides.realtime.mark_unseen", queue="short", user=user,
			job_id=f"cc-unseen-{user}", deduplicate=True)
	except Exception:
		frappe.logger("construction_core").exception("Desk's notification dot was not queued")


def mark_unseen(user: str):
	"""Desk's bell dot for a core notice (D-177). The worker retries a snapshot conflict or a lock wait: it retries only
	what it raises as RetryBackgroundJobError, and Frappe raises these as their own errors (background_jobs.py)."""
	from frappe.desk.doctype.notification_log.notification_log import set_notifications_as_unseen

	try:
		set_notifications_as_unseen(user)
	except (frappe.QueryDeadlockError, frappe.QueryTimeoutError) as e:
		frappe.db.rollback()
		raise frappe.RetryBackgroundJobError from e
