"""P3-13 (R-13; D-200, D-202): a turned-off account keeps no session.

Frappe ends a user's sessions on disable only inside a web request (its login manager), and `Session.resume` never
checks `enabled`, so a disable made by the console, a job, an import or `db.set_value` left live sessions for up to
170 h, and a live session could switch its own account back on (measured 2026-10-12). Here:

- `check_session` runs on every request (`auth_hooks`, after Frappe's API-key and OAuth checks): it reads `enabled` and
  the account's access stamp from the database, uncached, and refuses a session of a disabled account, or one that
  started before the account was last turned off or on. A refused request deletes its session (row and Redis entry),
  commits, and raises `frappe.AuthenticationError` itself, so Frappe clears the cookies and answers 401.
- `on_user_update` writes the stamp whenever a User document's `enabled` changes, and on a disable deletes the
  account's sessions inside the save's transaction (Redis entries after the commit).
- Sockets re-check every 60 s (`apps/construction_core/realtime/handlers.js`), and a turn-off is announced on the Redis
  channel `cc_session_end` so the socket server closes that account's sockets at once (D-203).
- `refuse_new_session` (`on_session_creation`) refuses a session started for a turned-off account by any sign-in path
  (an email link, a reset key, `login_as`); a turn-off also revokes the account's OAuth tokens and clears its
  password-reset key (D-203).
"""

import json
from contextlib import suppress


import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

STAMP = "cc_access_stamp"  # User custom field (setup/install.py), permlevel 1, hidden
SESSION_EXPIRY = "72:00"  # D-197: a session ends after 72 h without use (Frappe's default is 170 h)
EXEMPT = ("", "Guest", "Administrator")
CHANNEL = "cc_session_end"  # read by apps/construction_core/realtime/handlers.js


def check_session():
	"""auth_hooks: refuse the request of a turned-off account, or of a session older than its last turn-off or on."""
	user = frappe.session.user
	if not user or user in EXEMPT or (frappe.request and frappe.request.method == "OPTIONS"):
		return
	row = frappe.db.get_value("User", user, ["enabled", STAMP], as_dict=True)
	if row and cint(row.enabled) and not _older_than(row.get(STAMP)):
		return
	_refuse(account_off=user if not (row and cint(row.enabled)) else None)


def _older_than(stamp) -> bool:
	"""True when the session started before the stamp. A session made by an API key or a token has no start."""
	started = ((frappe.session.get("data") or {}).get("creation")) if frappe.session else None
	return bool(stamp and started and get_datetime(started) < get_datetime(stamp))


def _refuse(sid=None, account_off=None):
	"""Delete the session and refuse the request. For an account found turned off (by the console, a job or an
	import, which wrote no stamp), every other session of it goes too and the turn-off is stamped now, so a later
	re-enable revives none of them (P3-13 audit S1). The refusal is raised even when the database work fails (S3)."""
	sid = sid or frappe.session.sid
	try:
		if sid and sid != "Guest":
			frappe.db.delete("Sessions", {"sid": sid})
		if account_off:
			end_sessions(account_off)
			if frappe.db.exists("User", account_off):
				frappe.db.set_value("User", account_off, STAMP, now_datetime(), update_modified=False)
		frappe.db.commit()  # the request rolls back when it raises; the deletion must stay
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="construction_core: a refused session could not be deleted", defer_insert=True)
	if sid and sid != "Guest":
		frappe.cache.hdel("session", sid)
	if getattr(frappe.local, "cookie_manager", None):  # a web request (not a test or a job)
		from frappe.auth import clear_cookies

		clear_cookies()
		cookies = frappe.local.cookie_manager.cookies
		for key in set(frappe.local.cookie_manager.to_delete):
			cookies.pop(key, None)  # the request already queued `sid=<this session>`; send only the deletions
	raise frappe.AuthenticationError(_("Your access has ended. Please sign in again."))


def on_user_update(doc, method=None):
	"""User on_update: stamp every turn-off or turn-on; a turn-off also deletes the account's sessions."""
	before = doc.get_doc_before_save()
	if not before or cint(before.enabled) == cint(doc.enabled):
		return
	stamp = now_datetime()
	frappe.db.set_value("User", doc.name, STAMP, stamp, update_modified=False)
	doc.set(STAMP, stamp)  # a later save of this same object must not write the old value back (audit S2)
	if not cint(doc.enabled):
		end_sessions(doc.name)
		frappe.db.set_value("User", doc.name, "reset_password_key", None, update_modified=False)
		if frappe.db.table_exists("OAuth Bearer Token"):
			frappe.db.set_value("OAuth Bearer Token", {"user": doc.name, "status": "Active"}, "status", "Revoked")
		frappe.db.after_commit.add(lambda user=doc.name: announce_end(user))


def refuse_new_session(login_manager=None):
	"""on_session_creation: no session for a turned-off account, whatever signed it in (Frappe's `login_as` paths,
	such as an email link or a reset key, do not check `enabled`). The session row is already written: delete it."""
	user = getattr(login_manager, "user", None) or frappe.session.user
	if not user or user in EXEMPT or cint(frappe.db.get_value("User", user, "enabled")):
		return
	_refuse(getattr(frappe.local, "session_obj", None) and frappe.local.session_obj.sid)


def announce_end(user: str):
	"""Tell the socket server to close `user`'s sockets now; the 60 s check closes them anyway if this is lost."""
	from frappe.utils.background_jobs import get_redis_connection_without_auth

	with suppress(Exception):
		get_redis_connection_without_auth().publish(CHANNEL, json.dumps({"namespace": frappe.local.site, "user": user}))


def ensure_user_index():
	"""Frappe's Sessions table has no index on ``user``, so ending one account's sessions (here, and two-step sign-in's
	clean-up) scanned every row: slow on a busy site, and under snapshot isolation any other session written meanwhile
	made the delete fail with 1020 (seen at the P3-67 gate). Idempotent; after install and after every migrate."""
	frappe.db.add_index("Sessions", ["user"], "user_index")


def end_sessions(user: str):
	"""Delete every session of `user` in the current transaction; their Redis entries go once it commits."""
	table = frappe.qb.DocType("Sessions")
	sids = [r[0] for r in frappe.qb.from_(table).select(table.sid).where(table.user == user).run()]
	if not sids:
		return
	frappe.db.delete("Sessions", {"user": user})

	def drop_cached():
		for sid in sids:
			frappe.cache.hdel("session", sid)

	frappe.db.after_commit.add(drop_cached)


def pin_session_expiry():
	frappe.db.set_single_value("System Settings", "session_expiry", SESSION_EXPIRY)
