"""P3-56 (QE; firm set-up §4 Stage C, T6): a project's Team on its Settings page.

The project's Construction Managers (the permission type ``manage_team``) and System Managers add and remove team
accounts. Only an enabled team account is ever a target: never a client or a partner (D-262), Administrator, a System
Manager or an account with roles outside People's (people._kind). Every refused account answers like a missing one,
so a manager learns nothing about accounts they may not add. A client joins only through an invitation (D-198).
"""

import frappe
from frappe import _
from frappe.utils import cint

from construction_core.accounts import people
from construction_core.permissions import is_client, is_member, refuse_closed

NO_SUCH = "No team account has that email. Invite the person on People first."


def _project(project, write: bool):
	if is_client(frappe.session.user):
		raise frappe.DoesNotExistError(_("Not found"))  # job titles are the team's (QD)
	if not isinstance(project, str) or not frappe.db.exists("Construction Project", project):
		raise frappe.DoesNotExistError(_("Not found"))
	doc = frappe.get_doc("Construction Project", project)
	if not frappe.has_permission("Construction Project", "read", doc=doc):
		raise frappe.DoesNotExistError(_("Not found"))
	if write:
		frappe.has_permission("Construction Project", "manage_team", doc=doc, throw=True)
	return doc


def _team_account(person, enabled: bool = True) -> str:
	"""The stored account name of a team account (an enabled one unless ``enabled`` is False: a turned-off member is
	still taken off), found by name or email, or the one refusal."""
	name = None
	if isinstance(person, str) and person.strip():
		name = frappe.db.get_value("User", person.strip(), "name") or frappe.db.get_value("User",
			{"email": person.strip()}, "name")
	if not name or (enabled and not cint(frappe.db.get_value("User", name, "enabled"))) or is_client(name) \
			or people._kind(name, people._roles(name)) != "team":
		frappe.throw(_(NO_SUCH), frappe.DoesNotExistError)
	return name


@frappe.whitelist(methods=["GET"])
def list(project: str) -> list:  # noqa: A001 (the sheet's name); this module never calls the builtin
	"""The project's team members (no clients): [{user, full_name, job_title, role}]."""
	doc = _project(project, write=False)
	users = [r.user for r in doc.users if r.user and not is_client(r.user)]
	rows = frappe.get_all("User", filters={"name": ("in", users or [""])}, fields=["name", "full_name", "cc_job_title"])
	out = []
	for u in sorted(rows, key=lambda u: (u.full_name or u.name).lower()):
		roles = people._roles(u.name)
		role = next((r for r in people.TEAM_ROLES if r in roles), "System Manager" if "System Manager" in roles else None)
		out.append({"user": u.name, "full_name": u.full_name or u.name, "job_title": u.cc_job_title, "role": role})
	return out


@frappe.whitelist(methods=["POST"])
def add(project: str, person=None) -> dict:
	doc = _project(project, write=True)
	refuse_closed(project)
	person = _team_account(person)
	if not is_member(person, project):
		doc.append("users", {"user": person, "welcome_email_sent": 1})
		doc.save(ignore_permissions=True)  # manage_team was checked; the member guard still runs
		people._record(person, f"Added to project {project}")
	return {"project": project, "team": list(project)}


@frappe.whitelist(methods=["POST"])
def remove(project: str, person=None) -> dict:
	doc = _project(project, write=True)
	person = _team_account(person, enabled=False)
	if is_member(person, project):
		doc.set("users", [r for r in doc.users if r.user != person])
		doc.save(ignore_permissions=True)
		people._record(person, f"Removed from project {project}")
	return {"project": project, "team": list(project)}
