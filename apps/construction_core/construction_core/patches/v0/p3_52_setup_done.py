"""P3-52 (D-347): a site already in use (a project or a team account) has finished set-up, so its System Managers are
never sent to the wizard. Only a fresh site starts unfinished."""

import frappe
from frappe.utils import now_datetime

from construction_core.accounts.setup import DOCTYPE, finished

TEAM_ROLES = ("Construction Manager", "Construction Staff")


def in_use() -> bool:
	return bool(frappe.db.count("Construction Project") or frappe.db.exists("Has Role",
		{"parenttype": "User", "role": ("in", TEAM_ROLES), "parent": ("not in", ("Administrator", "Guest"))}))


def execute():
	if in_use() and not finished():
		frappe.db.set_single_value(DOCTYPE, "setup_finished_on", now_datetime())
