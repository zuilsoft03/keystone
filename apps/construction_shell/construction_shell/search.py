"""P3-08 (D-139, D-243): global search for the project team.

Staff only. The scope is explicit: one project the searcher may read, or every project they are a member of; an empty
scope finds nothing. In each project only the sections its rail shows are searched (Workspace Config, the same list
the frame reads). Records come through `frappe.get_list`, so the doctype's permissions and the §2.1 predicate decide;
Files through `get_all` within the project, then `has_permission` on each row (Frappe's File rule plus ours). A title
matches by its words; a name matches only exactly or by its short number ("12" finds RFI-…-0012). The typed text is
escaped for LIKE, so % and _ match themselves.
"""

import re

import frappe

from construction_core.permissions import allowed_projects
from construction_shell.api import _project_or_not_found, _staff_only
from construction_shell.records import RECORDS
from construction_shell.workspace_page import sections

# section -> (doctype, title field): the rail's searchable sections; Settings, Home and the client view hold no records
SOURCES = {key: (spec["doctype"], spec["title"]) for key, spec in RECORDS.items()}
SOURCES.update({"whiteboards": ("Whiteboard", "title"), "takeoff": ("CAD Drawing", "title"), "boq": ("BOQ", "title"),
	"discuss": ("Discuss Thread", "title")})
PER_SECTION, MAX_QUERY, MIN_QUERY = 6, 80, 2


def _like(text: str) -> str:
	return "%" + re.sub(r"([\\%_])", r"\\\1", text) + "%"


def _scope(project) -> list[str]:
	if project:
		_project_or_not_found(project)
		return [project]
	return [p for p in allowed_projects(frappe.session.user) if frappe.has_permission("Construction Project", "read", p)]


def _rail(projects: list[str]) -> dict[str, list[str]]:
	"""section -> the projects whose rail shows it; a project without a readable config shows nothing to search."""
	known = sections()["sections"]
	out: dict[str, list[str]] = {}
	for project in projects:
		if not (frappe.db.exists("Workspace Config", project) and frappe.has_permission("Workspace Config", "read", project)):
			continue
		for row in frappe.get_doc("Workspace Config", project).sidebar_sections:
			if row.visible and row.section in known:
				out.setdefault(row.section, []).append(project)
	return out


def _name_filters(q: str) -> list:
	out = [["name", "=", q]]
	if q.isdigit() and len(q) <= 6:  # a short number: the name's last part, at any of the widths our names use
		n = int(q)
		out += [["name", "like", f"%-{n:0{w}d}"] for w in (2, 3, 4, 5) if len(str(n)) <= w]
	return out


@frappe.whitelist(methods=["GET"])
def search(q=None, project=None) -> dict:
	_staff_only()
	q = (q if isinstance(q, str) else "").strip()[:MAX_QUERY]
	if len(q) < MIN_QUERY or (project is not None and not isinstance(project, str)):
		return {"results": []}
	projects = _scope(project or None)
	if not projects:
		return {"results": []}
	names = dict(frappe.get_all("Construction Project", filters={"name": ("in", projects)},
		fields=["name", "project_name"], as_list=True))
	rail = _rail(projects)
	results = []
	for section, (doctype, title) in SOURCES.items():
		scoped = rail.get(section)
		if not scoped:
			continue
		rows = frappe.get_list(doctype, filters=[[doctype, "project", "in", scoped]],
			or_filters=[[title, "like", _like(q)], *_name_filters(q)],
			fields=["name", f"{title} as title", "project"], order_by="modified desc", limit_page_length=PER_SECTION)
		results += [{"section": section, "doctype": doctype, "name": r.name, "title": r.title or r.name,
			"project": r.project, "project_name": names.get(r.project, r.project)} for r in rows]
	if rail.get("files"):
		found = 0
		# the bin is not searched, nor a file's earlier versions (P3-43, D-301)
		for f in frappe.get_all("File", filters={"cc_project": ("in", rail["files"]), "is_folder": 0, "cc_trashed": 0,
				"cc_version_of": ["is", "not set"]},
				or_filters=[["file_name", "like", _like(q)], ["name", "=", q]],
				fields=["name", "file_name", "cc_project"], order_by="modified desc", limit_page_length=PER_SECTION * 4):
			if found >= PER_SECTION:
				break
			if frappe.has_permission("File", "read", doc=f.name):  # Frappe's File rule and ours, row by row
				found += 1
				results.append({"section": "files", "doctype": "File", "name": f.name, "title": f.file_name,
					"project": f.cc_project, "project_name": names.get(f.cc_project, f.cc_project)})
	return {"results": results}
