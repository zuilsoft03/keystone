"""Off-host backup copies (P2-01, D-103, D-107): what deploy/backup.sh asks the site, and what it tells it.

Run by the backup service through `bench --site <site> execute construction_core.backups.<function>`, never over
the web (not whitelisted): the setting lives in Backup Settings, which only a System Manager edits.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

DEFAULT_KEEP_DAYS = 30
STATUSES = ("OK", "FAILED", "DISABLED")


def offsite_settings() -> dict:
	"""{enabled, keep_days}; defaults (on, 30 days) until a System Manager saves the setting. `bench execute` prints
	a returned dict as one line of JSON, which deploy/backup.sh reads."""
	# Field by field: the service's own record creates the Single without these two, and a missing field keeps its
	# default (on, 30 days) rather than reading as 0, which would switch copies off.
	values = frappe.db.get_singles_dict("Backup Settings")
	enabled = values.get("offsite_enabled")
	keep = cint(values.get("offsite_keep_days"))
	return {"enabled": 1 if enabled is None else cint(enabled), "keep_days": keep if keep >= 1 else DEFAULT_KEEP_DAYS}


def ensure_defaults() -> None:
	"""Write the setting's defaults where they are missing, so the Desk form shows what the service uses (on, 30
	days). Called by setup and before each record."""
	values = frappe.db.get_singles_dict("Backup Settings")
	missing = {k: v for k, v in (("offsite_enabled", 1), ("offsite_keep_days", DEFAULT_KEEP_DAYS)) if values.get(k) is None}
	if missing:
		frappe.db.set_single_value("Backup Settings", missing, update_modified=False)


def record_offsite(status: str, set_name: str, message: str = "") -> None:
	"""The backup service records the last copy's result, which a System Manager sees in Desk."""
	if status not in STATUSES:
		frappe.throw(_("Unknown status {0}").format(status))
	ensure_defaults()
	# set_single_value, not Document.db_set: on the staging site db_set returned without writing (found in P2-01).
	frappe.db.set_single_value("Backup Settings", {"last_offsite_status": status, "last_offsite_set": (set_name or "")[:140],
		"last_offsite_at": now_datetime(), "last_offsite_message": (message or "")[:1000]})


# P3-55 (firm set-up W6): the Backups panel. "Back up now" is Frappe's own backup (database and files) into the site's
# backups folder, queued on the long queue; the backup service's sets and their off-host copy stay as above.
JOB_ID = "cc_backup_now"
RUNBOOK = "RUNBOOK §10.5"


def _mark(step: str, state: str) -> None:
	from construction_core.accounts.setup import mark  # S1's module; imported when used

	mark(step, state)


@frappe.whitelist()
def state() -> dict:
	from frappe.utils.background_jobs import is_job_enqueued

	frappe.only_for("System Manager")
	values = frappe.db.get_singles_dict("Backup Settings")
	raw = values.get("last_backup_now")
	# The NAS is mounted in the backup service only; its last copy's result is what the site knows of the folder.
	return {"keep_days": offsite_settings()["keep_days"], "last": frappe.parse_json(raw) if raw else None,
		"running": is_job_enqueued(JOB_ID), "offsite_folder_present": values.get("last_offsite_status") == "OK",
		"runbook": RUNBOOK}


@frappe.whitelist(methods=["POST"])
def save(keep_days=None) -> dict:
	frappe.only_for("System Manager")
	ensure_defaults()
	s = frappe.get_doc("Backup Settings")
	s.offsite_keep_days = cint(keep_days)
	s.save()  # its validate refuses fewer than 1 day
	return state()


@frappe.whitelist(methods=["POST"])
def backup_now() -> dict:
	from frappe.utils.background_jobs import is_job_enqueued

	frappe.only_for("System Manager")
	if is_job_enqueued(JOB_ID):
		frappe.throw(_("A backup is already running."))
	frappe.enqueue("construction_core.backups.run_backup", queue="long", timeout=3 * 3600, job_id=JOB_ID,
		deduplicate=True, enqueue_after_commit=True)
	return {"queued": True}


def run_backup() -> None:
	"""The job behind backup_now (not whitelisted). Its result names a file in the site's backups folder only; an error's
	detail (which can hold paths) goes to the Error Log, the panel shows a plain line."""
	import os

	from frappe.utils.backups import new_backup

	try:
		odb = new_backup(ignore_files=False, force=True)
		parts = [p for p in (odb.backup_path_db, odb.backup_path_files, odb.backup_path_private_files) if p]
		last = {"ok": True, "at": str(now_datetime()), "size": sum(os.path.getsize(p) for p in parts),
			"path_hint": os.path.basename(odb.backup_path_db)}
	except Exception:
		frappe.log_error("Back up now failed")
		last = {"ok": False, "at": str(now_datetime()), "size": 0, "path_hint": "",
			"error": _("The backup failed. The Error Log has the details.")}
	frappe.db.set_single_value("Backup Settings", "last_backup_now", frappe.as_json(last))
	if last["ok"]:
		_mark("W6", "done")
