"""Server calls of the shell. Each one checks permission in its own body (DR-5); the app only presents.

The workspace is for staff (System Users); a client gets PermissionError here and uses the portal. Which projects and
records a user sees is decided by construction_core's predicate (DR-6) through `frappe.get_list` and
`has_permission`, never by these functions.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, today

from construction_core.core.counts import counts_for
from construction_core.discuss import inbox as chat_inbox
from construction_core.discuss import read as chat_read
from construction_core.permissions import is_client
from construction_shell import records
from construction_shell.workspace_page import is_staff, sections

LAST_PROJECT = "cc_last_project"  # frappe.defaults, per user (ARCHITECTURE §3.4)
# rail section -> its count key in construction_core.core.counts (sent live as cc_workspace_counts, DR-8)
COUNT_OF = {"rfi": "rfi_open", "submittals": "submittal_open", "variations": "vo_open"}
PROJECT_FIELDS = ["name", "project_name", "status", "cc_phase", "expected_start_date", "expected_end_date",
	"cc_contract_signed_on"]


def can_open_workspace() -> bool:
	"""The apps screen's permission hook (hooks.add_to_apps_screen): staff only; clients use the portal."""
	return is_staff(frappe.session.user)


def _staff_only():
	if not can_open_workspace():
		raise frappe.PermissionError(_("The workspace is for the project team."))


def _project_or_not_found(project: str) -> None:
	"""The same answer for a project that does not exist and one the user may not read (no existence leak)."""
	if not (project and isinstance(project, str) and frappe.db.exists("Construction Project", project)
			and frappe.has_permission("Construction Project", "read", project)):
		raise frappe.DoesNotExistError(_("Project not found"))


def _clients(projects: list[str]) -> dict[str, list[str]]:
	"""Client contacts per project (the members table, permlevel 1, which staff may read on their projects)."""
	rows = frappe.get_all("Project Member", filters={"parenttype": "Construction Project", "parent": ["in", projects],
		"cc_workspace_role": "Client"}, fields=["parent", "full_name", "user"], order_by="idx asc")
	out = {}
	for r in rows:
		out.setdefault(r.parent, []).append(r.full_name or r.user)
	return out


def _client_users(project: str) -> list[str]:
	"""The project's client contacts' accounts (the members table, which staff read on their projects)."""
	return frappe.get_all("Project Member", filters={"parenttype": "Construction Project", "parentfield": "users",
		"parent": project, "cc_workspace_role": "Client"}, pluck="user", order_by="idx asc")


def _chat_unread(project: str, user: str) -> int:
	"""Room messages by others the user has not read (§14.5), from the chat's own read of the user's visible messages."""
	rooms = frappe.get_list("Discuss Thread", filters={"project": project, "room_key": ["is", "set"]}, pluck="name",
		user=user)
	counts = chat_read.unread(user, project)
	return sum(counts.get(r, 0) for r in rooms)


def _with_handover(row: dict) -> dict:
	end = row.get("expected_end_date")
	row["handover_in_days"] = date_diff(end, today()) if end else None
	return row


def _sites(projects: list[str]) -> dict[str, dict]:
	"""P3-09 (D-138, D-157): each readable project's site, for whoever reads its permlevel-2 fields (the team, never a
	client); a project with no location has none, so a confidential project never shows on the map."""
	if not projects or 2 not in frappe.get_meta("Construction Project").get_permlevel_access("read"):
		return {}
	out = {}
	for r in frappe.get_all("Construction Project", filters={"name": ("in", projects)},
			fields=["name", "cc_latitude", "cc_longitude", "cc_site_place"]):
		if r.cc_latitude and r.cc_longitude:  # both, never 0 (validated on save)
			out[r.name] = {"lat": r.cc_latitude, "lng": r.cc_longitude, "place": r.cc_site_place or ""}
	return out


@frappe.whitelist(methods=["GET"])
def projects() -> dict:
	"""The projects dashboard: every project the user may read, with its counts, and the user's last project."""
	_staff_only()
	rows = frappe.get_list("Construction Project", fields=PROJECT_FIELDS, order_by="modified desc", limit=0)
	user = frappe.session.user
	clients = _clients([r.name for r in rows]) if rows else {}
	sites = _sites([r.name for r in rows])
	for r in rows:
		_with_handover(r)
		r["counts"] = counts_for(r.name, user)
		r["clients"] = clients.get(r.name, [])
		r["site"] = sites.get(r.name)
	last = frappe.defaults.get_user_default(LAST_PROJECT)
	return {
		"projects": rows,
		"last_project": last if any(r.name == last for r in rows) else None,
		"can_create": bool(frappe.has_permission("Construction Project", "create")),
		# P3-74: the top bar's Discussion inbox count, per active member project (one grouped read); the inbox and
		# Discuss pages keep it current through their own hosts, so no app-wide chat host reads it (F1)
		"inbox_unread": chat_inbox.unread_by_project(user, [r.name for r in rows if r.status not in chat_inbox.CLOSED]),
	}


@frappe.whitelist(methods=["POST"])
def set_last_project(project: str) -> None:
	_staff_only()
	_project_or_not_found(project)
	frappe.defaults.set_user_default(LAST_PROJECT, project)


@frappe.whitelist(methods=["GET"])
def project(project: str) -> dict:
	"""One project's frame: its header, its rail from Workspace Config, and the user's counts."""
	_staff_only()
	_project_or_not_found(project)
	rows = frappe.get_list("Construction Project", filters={"name": project}, fields=PROJECT_FIELDS)
	if not rows:  # the list predicate and has_permission disagree: answer as for any unreadable project
		raise frappe.DoesNotExistError(_("Project not found"))
	row = rows[0]
	known = sections()["sections"]
	rail, client_sections, portal_enabled = [{"section": "home"}], [], False
	if frappe.db.exists("Workspace Config", project) and frappe.has_permission("Workspace Config", "read", project):
		config = frappe.get_doc("Workspace Config", project)
		rail = [{"section": s.section} for s in config.sidebar_sections if s.visible and s.section in known]
		client_sections = [s.section for s in config.sidebar_sections if s.client_visible and s.section in known]
		portal_enabled = bool(config.client_portal_enabled)
	for item in rail:
		item["label"] = known[item["section"]]["label"]
		item["count_key"] = COUNT_OF.get(item["section"])
	return {
		"project": _with_handover(row),
		# What the Settings screen lets this user change; the server decides again on every save (D-123).
		"can_manage_portal": 1 in frappe.get_meta("Workspace Config").get_permlevel_access("write"),
		"can_manage_clients": bool(frappe.has_permission("Construction Project", "manage_clients", doc=project)),
		"rail": rail,
		"counts": counts_for(project, frappe.session.user),
		"clients": _clients([project]).get(project, []),
		# P3-64: who the chat's "Discuss with team" is for, and the rail's Discuss count (room messages not read yet)
		"client_users": _client_users(project),
		"chat_unread": _chat_unread(project, frappe.session.user),
		"client_sections": client_sections,
		"client_portal_enabled": portal_enabled,
	}


@frappe.whitelist(methods=["GET"])
def attention(project: str) -> dict:
	"""Project home: the open items with the nearest due dates (the user's own scoped lists)."""
	_staff_only()
	_project_or_not_found(project)
	rfis = frappe.get_list("RFI", filters={"project": project, "status": "Issued"},
		fields=["name", "subject", "due_date", "priority"], order_by="due_date asc", limit=5)
	submittals = frappe.get_list("Submittal", filters={"project": project, "status": "Under Review"},
		fields=["name", "title", "required_by"], order_by="required_by asc", limit=5)
	variations = frappe.get_list("Variation Order", filters={"project": project, "stage": "Change Order Request"},
		fields=["name", "title", "modified"], order_by="modified desc", limit=5)
	items = [{"section": "rfi", "name": r.name, "text": r.subject, "due": r.due_date, "priority": r.priority}
		for r in rfis]
	items += [{"section": "submittals", "name": s.name, "text": s.title, "due": s.required_by} for s in submittals]
	items += [{"section": "variations", "name": v.name, "text": v.title, "due": None} for v in variations]
	for item in items:
		item["due_in_days"] = date_diff(item["due"], today()) if item["due"] else None
	items.sort(key=lambda i: (i["due_in_days"] is None, i["due_in_days"] or 0))
	return {"items": items}


@frappe.whitelist(methods=["GET"])
def form_meta(section: str) -> dict:
	"""How a record section's list and form look (records.RECORDS). Not a permission: every read and save goes
	through frappe.client, where the doctype's permissions and its controller decide."""
	_staff_only()
	if section not in records.RECORDS:
		raise frappe.DoesNotExistError(_("Section not found"))
	return records.form_meta(section)


@frappe.whitelist(methods=["GET"])
def record_options(project: str) -> dict:
	"""The choices a record form offers in this project: its staff (for assignees and reviewers) and its files."""
	_staff_only()
	_project_or_not_found(project)
	users = frappe.get_all("Project Member", filters={"parenttype": "Construction Project", "parent": project},
		fields=["user", "full_name"], order_by="idx asc")
	files = frappe.get_all("File", filters={"cc_project": project, "is_folder": 0, "cc_trashed": ["in", [0, None]],
		"cc_version_of": ["is", "not set"]},  # P3-43 (D-301): a file's earlier versions are not offered
		fields=["name", "file_name", "file_url"], order_by="file_name asc")
	return {
		"members": [{"user": u.user, "name": u.full_name or u.user} for u in users if u.user and not is_client(u.user)],
		"files": [f for f in files if frappe.has_permission("File", "read", doc=f.name)],
	}
