"""The staff notification bell (P3-06; D-139, D-160, D-175): the reader's own notices, worded when they are read.

construction_core.notifications keeps what happened: the kind, the record, the actor and the from->to state. Here it
is worded with the glossary (words.json) in the reader's mode, linked to the workspace when the record's section is on
the project's rail and to Desk when it is not, and marked read. Every row is checked again when it is read: a record
that is gone, or that the reader may no longer read, is neither listed nor counted. Simple mode hides the question,
item-for-review and change notices, which stay unread for Advanced. Staff only: each method checks its caller in its
own body (DR-5) and reads or marks only the caller's own notices. The stored subject and texts are never returned.
"""

import html

import frappe
from frappe.utils import cint, get_absolute_url, get_fullname, strip_html

from construction_core import notifications as core
from construction_core.permissions import project_field
from construction_shell import records, words
from construction_shell.api import _staff_only
from construction_shell.preferences import mode_of
from construction_shell.workspace_page import known_path

SECTION_OF = {spec["doctype"]: s for s, spec in records.RECORDS.items()} | {"Discuss Thread": "discuss", "File": "files",
	"Construction Project": "settings",  # P3-16: a client joined or is waiting, seen in Settings → Client contacts
	"File Request": "discuss",  # P3-71: files sent, asked for again, or a reminder
	"Approval Request": "discuss",  # P3-78: approvals live in the Discussion section (approvals design §3.12)
	"Approval Route": "settings"}  # P3-82: a route changed, seen in Settings → Approval steps (§14.6); site-level
TITLE_OF = {spec["doctype"]: spec["title"] for spec in records.RECORDS.values()} | {"Discuss Thread": "title",
	"File": "file_name", "Construction Project": "project_name", "File Request": "title",
	"Approval Request": "subject_title", "Approval Route": "record_kind"}
# linked to their section, not to an item in it
SECTION_LEVEL = ("File", "Construction Project", "File Request", "Approval Request", "Approval Route")
SITE_LEVEL = ("Approval Route",)  # no project: linked to Desk
SHOWN, MAX_LIMIT, SCAN, PAGE = 20, 50, 200, 50  # the badge reads "20+" past SHOWN; a list reads at most SCAN rows


class _Blank(dict):
	def __missing__(self, key):
		return ""


def _plain(value, limit=120) -> str:
	return html.unescape(strip_html(str(value or ""))).replace("<", "").replace(">", "").strip()[:limit]


def _mode(mode, user) -> str:
	"""The screen's mode when it sends one (display only, it never widens a read), else the reader's own."""
	return words.normal(mode) if mode else mode_of(user)


def _skip(mode) -> tuple:
	if mode == words.ADVANCED:
		return ()
	hidden = set(words.glossary()["notices"]["advanced_sections"])
	return tuple(doctype for doctype, section in SECTION_OF.items() if section in hidden)


def _reads():
	return frappe._dict(records={}, rails={})


def _record(doctype, name, reads):
	"""The record as the reader may see it now, or None: gone, or no longer theirs to read."""
	if (doctype, name) not in reads.records:
		reads.records[(doctype, name)] = _read(doctype, name)
	return reads.records[(doctype, name)]


def _read(doctype, name):
	if not (name and frappe.db.exists(doctype, name)):
		return None
	try:
		if not frappe.has_permission(doctype, "read", doc=name):
			return None
	except frappe.DoesNotExistError:
		frappe.clear_last_message()
		return None
	fields = {"title": TITLE_OF[doctype], **({} if doctype in SITE_LEVEL else {"project": project_field(doctype)})}
	if doctype == "File":
		fields["folder"] = "folder"
	row = frappe.db.get_value(doctype, name, list(fields.values()), as_dict=True) or {}
	return frappe._dict({key: row.get(field) for key, field in fields.items()})


def _items(user, mode, *, unread_only, want, reads) -> list:
	"""The reader's notices that they may still read, newest first. The unread client messages of one conversation are
	one item, and so are its unread replies (P3-69), so a notice written twice by two posts at once still shows once."""
	skip, items, together = _skip(mode), [], set()
	for start in range(0, SCAN, PAGE):
		page = core.notices_of(user, unread_only=unread_only, skip_doctypes=skip, start=start, page_length=PAGE)
		for n in page:
			grouped = n.kind in core.GROUPED and not n.read
			if grouped and (n.kind, n.docname) in together:
				continue
			record = _record(n.doctype, n.docname, reads)
			if not record:
				continue
			if grouped:
				together.add((n.kind, n.docname))
			items.append((n, record))
			if len(items) >= want:
				return items
		if len(page) < PAGE:
			break
	return items


def _count(user, mode, reads) -> dict:
	n = len(_items(user, mode, unread_only=True, want=SHOWN + 1, reads=reads))
	return {"unread": min(n, SHOWN), "more": n > SHOWN}


def _rail(project, reads) -> set:
	"""The sections on the project's rail, read as the frame reads them (api.project_frame); Home always."""
	if project not in reads.rails:
		on = {"home"}
		if frappe.db.exists("Workspace Config", project) and frappe.has_permission("Workspace Config", "read", project):
			on |= {s.section for s in frappe.get_doc("Workspace Config", project).sidebar_sections if s.visible}
		reads.rails[project] = on
	return reads.rails[project]


def _link(n, record, section, reads):
	"""(route, query, href): the workspace when the record's section is on its project's rail, else Desk (D-175)."""
	project = record.project
	if project and section in _rail(project, reads):
		parts = [project, section] if n.doctype in SECTION_LEVEL else [project, section, n.docname]
		if known_path("/workspace/" + "/".join(parts)):
			route = {"project": project, "section": section} | ({"item": n.docname} if len(parts) == 3 else {})
			return route, ({"folder": record.folder} if n.doctype == "File" and record.folder else {}), None
	return None, None, get_absolute_url(n.doctype, n.docname)


def _item(n, record, mode, reads) -> dict:
	section = SECTION_OF[n.doctype]
	actor = _plain(get_fullname(n.actor)) or n.actor
	values = {"actor": actor, "title": _plain(record.title) or n.docname, "noun": words.noun(section, mode),
		"from": words.state_label(n.from_state, mode) or "", "to": words.state_label(n.to_state, mode) or ""}
	route, query, href = _link(n, record, section, reads)
	return {
		"name": n.id,
		"kind": n.kind,
		"text": words.glossary()["notices"]["kinds"][n.kind][mode].format_map(_Blank(values)),
		"actor": {"name": actor, "image": frappe.get_cached_value("User", n.actor, "user_image")},
		"when": str(n.creation),
		"read": n.read,
		"route": route,
		"query": query,
		"href": href,
	}


@frappe.whitelist(methods=["GET"])
def feed(limit: int | str = SHOWN, mode: str | None = None) -> dict:
	"""The caller's latest notices and how many are unread, worded in `mode`."""
	_staff_only()
	user = frappe.session.user
	mode, reads = _mode(mode, user), _reads()
	want = min(max(cint(limit), 1), MAX_LIMIT)
	items = [_item(n, record, mode, reads) for n, record in _items(user, mode, unread_only=False, want=want, reads=reads)]
	return {"items": items, **_count(user, mode, reads), "mode": mode}


@frappe.whitelist(methods=["POST"])
def mark_read(name: str, mode: str | None = None) -> dict:
	"""Mark one of the caller's notices read; a grouped item (client messages, replies) with its conversation's other
	unread notices of that kind."""
	_staff_only()
	user = frappe.session.user
	core.mark_notice_read(user, str(name))
	return _count(user, _mode(mode, user), _reads())


@frappe.whitelist(methods=["POST"])
def mark_all_read(mode: str | None = None) -> dict:
	"""Mark the caller's notices read. In Simple, the notices it hides stay unread for Advanced (D-175)."""
	_staff_only()
	user = frappe.session.user
	mode = _mode(mode, user)
	core.mark_all_notices_read(user, _skip(mode))
	return _count(user, mode, _reads())
