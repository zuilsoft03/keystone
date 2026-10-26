"""P3-43 (D-301): File gets its revision fields, and the version rows the Office saves made before them are linked
to their file and lettered.

Each such row is named ``base (vYYYYmmdd-HHMMSS).ext`` and holds the content its file had before a save. Its file is
the one whose save's Activity line names it ("... the previous version is kept as <name>"), which follows the file
wherever it was moved. A row no Activity line names is left alone: an upload that only looks like a version is not
taken for one (P3-43 audit note 3). Drafts (``(edited ...)``) are not versions and stay as they are, and so do
trashed rows. A version row that was itself saved in Office (it was an ordinary file then) is followed back to the
file at the root of the chain, so every version hangs off one working file (P3-43 review).

Authors are rebuilt from the saves: Rev A is the file's owner at its creation; each later revision is by whoever
saved it, at that save (the owner and creation of the version row that save made)."""

import html
import re
from collections import defaultdict

import frappe
from frappe.utils import strip_html

from construction_core.files.versions import letter
from construction_core.setup.install import setup

STAMPED = re.compile(r"^(?P<base>.+) \(v\d{8}-\d{6}\)(?P<ext>\.[^.\s]+)?$")
KEPT = re.compile(r"the previous version is kept as (?P<name>.+?)\s*$")
SAVED = "Saved in Office"


def execute():
	setup()
	rows = frappe.get_all("File", filters={"is_folder": 0, "cc_version_of": ["is", "not set"],
		"cc_trashed": ["in", [0, None]], "file_name": ["like", "% (v%)%"]},
		fields=["name", "file_name", "folder", "cc_project", "owner", "creation"], order_by="creation asc")
	rows = [r for r in rows if r.cc_project and STAMPED.match(r.file_name)]
	if not rows:
		return
	kept = defaultdict(set)  # a version row's name -> the files whose save says it kept it
	for c in frappe.get_all("Comment", filters={"reference_doctype": "File", "comment_type": "Info",
			"content": ["like", "%previous version is kept as%"]}, fields=["reference_name", "content"]):
		m = KEPT.search(html.unescape(strip_html(c.content or "")))  # stored escaped (R&amp;D Plan)
		if m:
			kept[m["name"]].add(c.reference_name)
	parent = {}
	for r in rows:
		found = [f for f in kept.get(r.file_name, ()) if _working(f, r.cc_project)]
		if len(found) == 1 and found[0] != r.name:
			parent[r.name] = found[0]
	links = defaultdict(list)
	for r in rows:
		root, seen = parent.get(r.name), {r.name}
		while root in parent and root not in seen:  # a version saved in Office: follow it back to its file
			seen.add(root)
			root = parent[root]
		if root and root not in seen:
			links[root].append(r)
	for file, versions in links.items():
		w = frappe.db.get_value("File", file, ["owner", "creation"], as_dict=True)
		by, on, note = w.owner, w.creation, ""
		for i, v in enumerate(sorted(versions, key=lambda v: v.creation), 1):
			frappe.db.set_value("File", v.name, {"cc_version_of": file, "cc_rev": letter(i), "cc_rev_by": by,
				"cc_rev_on": on, "cc_rev_note": note, "cc_client_visible": 0}, update_modified=False)
			by, on, note = v.owner, v.creation, SAVED
		frappe.db.set_value("File", file, {"cc_rev": letter(len(versions) + 1), "cc_rev_by": by, "cc_rev_on": on,
			"cc_rev_note": note}, update_modified=False)


def _working(file: str, project: str) -> bool:
	row = frappe.db.get_value("File", file, ["cc_project", "is_folder", "cc_version_of"], as_dict=True)
	return bool(row and row.cc_project == project and not row.is_folder and not row.cc_version_of)
