"""Staff "View as client" (P3-05, D-136): what one client contact of a project sees in the portal, read-only.

Every read is the client's own: the shared core reads take ``user=<client>`` (portal.project_view, portal_api
.client_payload, discuss.api.client_thread_view, whiteboard.api.board_data), so the §2.1 predicate, the client rules
(§2.5), the switches (D-098, D-117) and that client's shares decide (DR-6). Nothing switches the session.

Every record returned is also one the caller reads; the rest is dropped, never named or counted. GET only: nothing is
written, published or remembered. The client is named by a Project Member row of the project (``contact``), which only
``client_of`` turns into a user, after checking the caller (DR-5). The core never reads the shell's view mode (rule 3d):
the shell asks for the client's mode itself.
"""

import frappe
from frappe import _
from frappe.utils import get_fullname

from construction_core import portal, portal_api
from construction_core.discuss import api as chat_api
from construction_core.discuss import view as chat_view
from construction_core.discuss.provider import PAGE
from construction_core.permissions import CLIENT_ROLE, _bypass, is_client, switches_once
from construction_core.whiteboard import api as board_api

# The client payload's record lists. A list the payload gains without an entry here makes the preview refuse (fail
# closed), so no new part of the portal reaches staff without the caller's check.
BOUNDED = {"files": "File", "documents": "Project Document", "rfis": "RFI", "submittals": "Submittal",
	"variations": "Variation Order", "whiteboards": "Whiteboard", "threads": "Discuss Thread",
	"approvals": "Approval Request"}  # P3-79: the Approvals tab's requests, each also read by the caller
UNBOUNDED = frozenset({"project", "sections_off", "upload", "closed"})  # the project; the switches; what send_file
# accepts; whether it is closed (P3-59)


def _not_found():
	return frappe.DoesNotExistError(_("Not found"))


def _check_caller(project) -> None:
	"""The caller is the project team (a System User; the core restates the workspace's rule, never imports the
	shell), reads the project and its members table (permlevel 1: the contacts are its rows)."""
	user = frappe.session.user
	if user == "Guest" or frappe.get_cached_value("User", user, "user_type") != "System User":
		raise frappe.PermissionError(_("The client view is for the project team."))
	if not (isinstance(project, str) and portal.can_read_project(project)):
		raise _not_found()
	if 1 not in frappe.get_meta("Construction Project").get_permlevel_access("read", user=user):
		raise _not_found()


def _previewable(user) -> bool:
	"""A client who has a real portal view: an enabled Website User with the client role, never a bypass account."""
	return (bool(user) and user not in ("Administrator", "Guest") and is_client(user)
		and CLIENT_ROLE in frappe.get_roles(user) and not _bypass(user)
		and bool(frappe.db.get_value("User", user, "enabled")))


def _client_rows(project: str) -> list:
	rows = frappe.get_all("Project Member", filters={"parenttype": "Construction Project", "parentfield": "users",
		"parent": project}, fields=["name", "user"], order_by="idx asc")
	return [r for r in rows if _previewable(r.user)]


def client_of(project: str, contact: str) -> str:
	"""Not whitelisted: the one place a request value becomes a user. Checks the caller first (DR-5); a row that is not
	a previewable client of this project answers as a missing one."""
	_check_caller(project)
	row = frappe.db.get_value("Project Member", contact, ["parent", "parenttype", "parentfield", "user"],
		as_dict=True) if isinstance(contact, str) and contact else None
	if (not row or (row.parenttype, row.parentfield, row.parent) != ("Construction Project", "users", project)
			or not _previewable(row.user)):
		raise _not_found()
	return row.user


def _caller_reads(doctype: str, name) -> bool:
	# frappe.has_permission with throw=False prints nothing; Document.has_permission would message the caller.
	return bool(frappe.has_permission(doctype, "read", doc=name, throw=False))


def _both_read(doctype: str, name, project: str, client: str) -> bool:
	return (isinstance(name, str) and bool(name) and frappe.db.get_value(doctype, name, "project") == project
		and bool(frappe.has_permission(doctype, "read", doc=name, user=client, throw=False))
		and _caller_reads(doctype, name))


def _bounded(data: dict, client: str) -> dict:
	"""The payload's record lists, each bounded by the caller's reads. Each thread's messages and their cards go through
	the chat's one exit with the caller (discuss.view.respond): every nested card is checked too (SEC-9)."""
	if set(data) != set(BOUNDED) | UNBOUNDED:
		raise frappe.ValidationError("The client view does not know every part of the portal payload")
	for key, doctype in BOUNDED.items():
		ident = "_file" if key == "files" else "name"  # P3-07: files carry no "name", only the internal id
		data[key] = [r for r in data[key] if _caller_reads(doctype, r[ident])]
	return portal_api.answer(data, user=client, caller=frappe.session.user)


@frappe.whitelist(methods=["GET"])
def contacts(project: str) -> list:
	"""The project's client contacts a staff member may view as: the row (``contact``) and the name."""
	_check_caller(project)
	return [{"contact": r.name, "name": get_fullname(r.user)} for r in _client_rows(project)]


@frappe.whitelist(methods=["GET"])
def preview(project: str, contact: str) -> dict:
	"""The portal's answer for one project as this client gets it, limited to what the caller reads."""
	client = client_of(project, contact)
	is_open = portal.can_read_project(project, user=client)
	return {"contact": contact, "client_name": get_fullname(client), "portal_open": is_open,
		"data": _bounded(portal_api.client_payload(project, user=client), client) if is_open else None}


@frappe.whitelist(methods=["GET"])
def preview_thread(project: str, contact: str, thread: str) -> dict:
	"""One conversation as this client reads it (no staff notes, pins or read state), limited to what the caller reads."""
	client = client_of(project, contact)
	if not _both_read("Discuss Thread", thread, project, client):
		raise _not_found()
	memo = {}
	view = chat_api.client_thread_view(frappe.get_doc("Discuss Thread", thread), user=client, memo=memo)
	return chat_api.legacy_view(chat_view.respond(view, client, caller=frappe.session.user, memo=memo))


# P3-64 (F1): the chat in the core shape, as the client reads it, so the preview draws what the client's portal draws:
# the rooms and threads with their reply lines, a thread's page and its older pages, and a thread's root. Each read is
# the client's own (discuss.api with viewer=client) and bounded by the caller's reads (caller=the session user).
# GET only: no read state, follow or notice is written.


@frappe.whitelist(methods=["GET"])
def preview_threads(project: str, contact: str) -> list:
	"""The project's threads as this client reads them (their unread and follows too), less those the caller does not
	read."""
	client = client_of(project, contact)
	if not portal.can_read_project(project, user=client):
		raise _not_found()
	return chat_api._threads(project, viewer=client, caller=frappe.session.user)


@frappe.whitelist(methods=["GET"])
def preview_messages(project: str, contact: str, thread: str, cursor: str | None = None) -> dict:
	"""One page of a conversation as this client reads it, newest first, limited to what the caller reads."""
	client = client_of(project, contact)
	if not _both_read("Discuss Thread", thread, project, client):
		raise _not_found()
	with switches_once():
		return chat_api._messages(thread, cursor, PAGE, viewer=client, caller=frappe.session.user)


@frappe.whitelist(methods=["GET"])
def preview_message(project: str, contact: str, name: str) -> dict:
	"""One message as this client reads it (a thread's root), limited to what the caller reads."""
	client = client_of(project, contact)
	thread = frappe.db.get_value("Discuss Message", name, "thread") if isinstance(name, str) and name else None
	if not _both_read("Discuss Thread", thread, project, client):
		raise _not_found()
	with switches_once():
		return chat_api._message(name, viewer=client, caller=frappe.session.user)


@frappe.whitelist(methods=["GET"])
def preview_board(project: str, contact: str, board: str) -> dict:
	"""One board as this client opens it (view only)."""
	client = client_of(project, contact)
	if not _both_read("Whiteboard", board, project, client):
		raise _not_found()
	return board_api.board_data(frappe.get_doc("Whiteboard", board), user=client)
