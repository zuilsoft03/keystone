"""P3-58 (firm set-up §4 Stage F; T7, T9): the Company page and the dashboard's Getting started checklist.

System Managers only, in every body: the page carries the firm's details, the mail and backup state and the set-up
progress, which no other account reads (T7, T9). Each section is the reader its wizard panel uses; a reader that is
not installed answers {} for its section. Clients are persons with company text (QF); Partner companies come with
P3-27 (D-444).
"""

import importlib
import shutil

import frappe
from frappe import _

import construction_core
from construction_core.onboarding import privacy

# The Company page's section (its anchor) for each wizard step; W8 has none: a skipped first project is made from
# the dashboard's Create project.
STEPS = {"W1": ("Your firm", "firm"), "W2": ("Your brand", "brand"), "W3": ("Outgoing email", "mail"),
	"W4": ("Your own account", "people"), "W5": ("Two-step sign-in", "security"), "W6": ("Backups", "backups"),
	"W7": ("Project defaults", "defaults"), "W8": ("Your first project", "projects"), "W9": ("Your team", "people"),
	"W10": ("Your client", "clients")}
DISMISSED = "cc_setup_checklist_dismissed"  # a site default: one System Manager's dismissal is the firm's


def _read(module: str, fn: str) -> dict:
	"""Another slice's reader, or {} where it is not installed yet."""
	try:
		reader = getattr(importlib.import_module(module), fn, None)
	except ImportError:
		return {}
	return reader() if reader else {}


def _clients() -> list[dict]:
	rows = frappe.get_all("Client Profile", fields=["account", "company_name"], order_by="account asc")
	users = {u.name: u for u in frappe.get_all("User", filters={"name": ("in", [r.account for r in rows] or [""])},
		fields=["name", "full_name", "email"])}
	member = frappe.get_all("Project Member", filters={"parenttype": "Construction Project",
		"user": ("in", list(users) or [""])}, fields=["user", "parent"])
	names = dict(frappe.get_all("Construction Project", filters={"name": ("in", [m.parent for m in member] or [""])},
		fields=["name", "project_name"], as_list=True))
	projects = {}
	for m in member:
		projects.setdefault(m.user, []).append(names.get(m.parent) or m.parent)
	return [{"full_name": users[r.account].full_name or r.account, "email": users[r.account].email or r.account,
		"company": r.company_name, "projects": sorted(projects.get(r.account, []))} for r in rows if r.account in users]


def _health(backups: dict) -> dict:
	from frappe.utils.scheduler import is_scheduler_inactive

	free = shutil.disk_usage(frappe.get_site_path()).free
	return {"scheduler_on": not is_scheduler_inactive(), "mail_queue_errors": frappe.db.count("Email Queue",
		{"status": "Error"}), "last_backup": backups.get("last"), "disk_free": f"{free / 1e9:.1f} GB",
		"app_version": construction_core.__version__}


def _checklist(state: dict) -> list[dict]:
	steps, hidden = state.get("steps") or {}, set(state.get("hidden") or ())
	return [{"step": step, "title": title, "section": section} for step, (title, section) in STEPS.items()
		if step not in hidden and (steps.get(step) or {}).get("state") == "skipped"]


@frappe.whitelist(methods=["GET"])
def page() -> dict:
	frappe.only_for("System Manager")
	from construction_core import brand
	from construction_core.accounts import two_step

	setup = _read("construction_core.accounts.setup", "state")
	backups = _read("construction_core.backups", "state")
	return {"firm": setup.get("firm") or {}, "brand": brand.public(),
		"mail": _read("construction_core.accounts.mail_setup", "get"), "backups": backups,
		"security": two_step.requirement_status(), "clients": _clients(),
		"privacy": {"contact": privacy.contact(), "notice_version": privacy.VERSION}, "health": _health(backups),
		"checklist": _checklist(setup), "checklist_dismissed": _dismissed()}


def _dismissed() -> bool:
	# the stored row, not frappe's per-user defaults cache, which can still hold the value from before the dismissal
	return bool(frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": DISMISSED}, "defvalue"))


@frappe.whitelist(methods=["POST"])
def dismiss_checklist() -> dict:
	frappe.only_for("System Manager")
	frappe.db.set_default(DISMISSED, "1")
	return {"checklist_dismissed": True}
