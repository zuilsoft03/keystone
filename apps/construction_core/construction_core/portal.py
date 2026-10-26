"""Minimal client portal (P1-13, D-089): what a client may see of one project, and posting in client threads.

Every read goes through ``frappe.get_list`` or a per-record ``has_permission``, so the §2.1 predicate and the client
rules (§2.5) decide; the portal adds no access of its own (DR-6). Approvals are not in the MVP portal.

The reads take ``user`` (None: the session user, today's behaviour). The staff preview (P3-05, D-136) passes the client
it shows, so every read there is that client's own. A read below without ``user=`` would show the preview the caller's
own records instead.
"""

import html

import frappe
from frappe import _
from frappe.utils import strip_html

from construction_core.discuss import read as chat_read
from construction_core.discuss.checks import MAX_MESSAGE  # noqa: F401  (send_file's message limit)
from construction_core.discuss.provider import DiscussChat
from construction_core.permissions import is_client


def my_projects() -> list:
	return frappe.get_list("Construction Project", fields=["name", "project_name", "status", "cc_phase"], order_by="project_name asc")


def can_read_project(project: str, user: str | None = None) -> bool:
	return (
		bool(project)
		and bool(frappe.db.exists("Construction Project", project))
		and frappe.has_permission("Construction Project", "read", doc=project, user=user)
	)


def project_view(project: str, user: str | None = None, room_only: bool = False) -> dict:
	"""Everything the portal shows for one project, as ``user`` reads it. The caller has checked ``can_read_project``.
	Each thread holds its newest 50 messages (F2); ``room_only`` (the server-rendered page, P3-64) reads them for the
	Client room alone, the one conversation that page shows."""
	chat = DiscussChat()
	threads = chat_read.rooms_first(frappe.get_list("Discuss Thread", filters={"project": project},
		fields=["name", "title", "project", "audience", "anchor_doctype", "anchor_name", "status", "room_key",
		"in_room"], order_by="creation asc", user=user))  # the Client room first (P3-73)
	for t in threads:
		t.messages = chat.messages(t.name, user=user) if (t.room_key or not room_only) else []
		for m in t.messages:
			m.author_name = frappe.utils.get_fullname(m.author)
			m.when = frappe.utils.pretty_date(m.creation)
			# Frappe stores text fields sanitised as HTML; the portal shows plain text and the template escapes it.
			m.text = html.unescape(strip_html(m.content or ""))
			if not m.text and (m.get("kind") == "Files" or m.get("file")):
				m.text = _("Files")  # P3-65: a message of files with no caption is named by its kind, never a blank bubble
			elif not m.text and m.get("kind") == "Voice":
				m.text = _("Voice message")  # P3-67: the same for a voice note with no caption
	variations = frappe.get_list("Variation Order", filters={"project": project},
		fields=["name", "title", "stage", "vo_delta_sum"], order_by="creation desc", user=user)
	for v in variations:
		v.amount = frappe.format_value(v.vo_delta_sum, {"fieldtype": "Currency"})
	return {
		# Only the fields the page shows: the template never holds the Project's internal (permlevel 2) fields.
		"project": frappe.db.get_value("Construction Project", project, ["name", "project_name", "status", "cc_phase"], as_dict=True),
		"files": client_files(project, user=user),
		"documents": frappe.get_list("Project Document", filters={"project": project},
			fields=["name", "document_number", "revision", "title"], order_by="document_number asc", user=user),
		"rfis": frappe.get_list("RFI", filters={"project": project},
			fields=["name", "subject", "status", "due_date", "response"], order_by="creation desc", user=user),
		"submittals": frappe.get_list("Submittal", filters={"project": project},
			fields=["name", "title", "status", "current_revision"], order_by="creation desc", user=user),
		"variations": variations,
		"threads": threads,
		"whiteboards": frappe.get_list("Whiteboard", filters={"project": project}, fields=["name", "title", "last_saved_on"],
			order_by="modified desc", user=user),
	}


def board_view(project: str, board: str) -> dict | None:
	"""A client-visible board of the project, or None (the caller answers 404)."""
	row = frappe.db.get_value("Whiteboard", board, ["name", "title", "project"], as_dict=True)
	if not row or row.project != project or not frappe.has_permission("Whiteboard", "read", doc=board):
		return None
	return {"board": row, "project": frappe.db.get_value("Construction Project", project, ["name", "project_name"], as_dict=True)}


def client_files(project: str, user: str | None = None) -> list:
	"""Files of the project ``user`` may download: the shared ones and, until shared, the ones they sent themselves
	(P3-07, D-158). A file sent in a conversation shows there, not here. Frappe's own File list rule limits
	non-System users to files they own, so candidates are found here and each one is checked with the same rule a
	download uses."""
	viewer = user or frappe.session.user
	rows = frappe.get_all("File", filters={"cc_project": project, "is_folder": 0, "cc_trashed": 0},
		or_filters={"cc_client_visible": 1, "owner": viewer},
		fields=["name", "file_name", "file_url", "file_size", "owner", "cc_client_visible", "attached_to_doctype"],
		order_by="creation desc")
	return [r for r in rows if r.attached_to_doctype != "Discuss Thread"
		and frappe.has_permission("File", "read", doc=r.name, user=user)]


@frappe.whitelist(methods=["POST"])
def post_message(thread: str, content: str) -> str:
	"""A client posts in a thread it may read, on the one send path: the portal checks, then the claim (D-387)."""
	content = (content or "").strip()
	if not content:
		frappe.throw(_("Write a message first"))
	if len(content) > MAX_MESSAGE:
		frappe.throw(_("A message is at most {0} characters").format(MAX_MESSAGE))
	if not is_client(frappe.session.user):
		frappe.throw(_("Staff post from Desk"), frappe.PermissionError)
	return DiscussChat().post(thread, content)
