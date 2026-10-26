"""The client portal's data as JSON, for a portal presented by a single-page app (P2-06, D-121).

The same reads as the server-rendered portal (``portal.project_view``): every list goes through ``frappe.get_list`` or a
per-record ``has_permission``, so the §2.1 predicate, the client rules (§2.5), the section switches (D-098) and the
portal switch (D-117) decide. Clients only: staff use the workspace. Text fields are plain text; the app escapes them.

``send_file`` (P3-07) is the one way a client adds a file to a project in Files; a conversation's files go through the
chat's upload and send (P3-65).
``open_thread`` (QR-2, D-415) is the one way a client opens a thread: on a message of the Client room.
"""

import html
import time

import frappe
from frappe import _
from frappe.utils import cint, strip_html
from frappe.utils.file_manager import MaxFileSizeReachedError

from construction_core import client_files, portal, projects_close
from construction_core import scan_holds
from construction_core.approvals import waiting
from construction_core.client_files import CLIENT_TYPES, MODEL_TYPES, client_limit, type_limit
from construction_core.discuss import api as chat_api
from construction_core.discuss import read as chat_read
from construction_core.discuss import rooms as chat_rooms
from construction_core.discuss import view as chat_view
from construction_core.discuss.registry import ViewCtx
from construction_core.notifications import CLIENT_FILE, notify
from construction_core.permissions import client_section_open, client_sections_off, is_client, refuse_closed
from construction_core.providers.storage import CLIENT_INBOX, get_storage
from construction_core.workspace import client_folders, root_path


def _clients_only():
	if not is_client(frappe.session.user):
		frappe.throw(_("The portal is for clients; the project team uses the workspace"), frappe.PermissionError)


def _text(value) -> str:
	return html.unescape(strip_html(value or ""))


@frappe.whitelist(methods=["GET"])
def projects() -> list:
	_clients_only()
	return portal.my_projects()


@frappe.whitelist(methods=["GET"])
def project_data(project: str) -> dict:
	"""What the portal shows of one project. A missing project and one the client may not read answer the same."""
	_clients_only()
	if not portal.can_read_project(project):
		raise frappe.DoesNotExistError(_("Not found"))
	return answer(client_payload(project))


def client_payload(project: str, user: str | None = None) -> dict:
	"""The portal's answer for one project, as ``user`` (None: the session user) reads it. The caller has checked
	``portal.can_read_project(project, user=user)``. The staff preview (P3-05) shows exactly this for its client.
	Files carry an internal ``_file`` and message cards a ``_ref``, for the preview's own check: every caller that
	answers a request passes the payload through ``answer``, so no client gets a raw File id (P3-07)."""
	viewer = user or frappe.session.user
	view = portal.project_view(project, user=user)
	for r in view["rfis"]:
		r.response = _text(r.response)
	memo = {}
	threads = []
	for t in view["threads"]:
		ctx = ViewCtx(user=viewer, thread=t, staff=False, memo=memo)
		threads.append({"name": t.name, "title": chat_read.title_for(ctx, t), "status": t.status,
			"messages": chat_view.present(ctx, t.messages)})
	view["threads"] = threads
	view["files"] = [{"_file": f.name, "file_name": f.file_name, "url": f.file_url, "size": cint(f.file_size),
		"mine": f.owner == viewer, "shared": bool(f.cc_client_visible)} for f in view["files"]]
	# P3-79 (§3.12): the approvals group needs the project's Portal approvals switch as well as its section
	off = client_sections_off(project) | (set() if cint(frappe.db.get_value("Construction Project", project,
		"cc_portal_approvals")) else {"approvals"})
	view["sections_off"] = sorted(off)
	view["approvals"] = [] if "approvals" in off else waiting.rows(project, viewer)
	view["closed"] = projects_close.closed_state(project)  # P3-59: the portal shows a closed project as read only
	# what send_file accepts (P3-07); P3-75 (D-417): model files up to the site's ceiling, every other type 100 MB
	view["upload"] = {"types": list(CLIENT_TYPES), "max_bytes": client_limit(), "max_other_bytes": type_limit("pdf"),
		"model_types": sorted(MODEL_TYPES.intersection(CLIENT_TYPES))}
	return view


@frappe.whitelist(methods=["GET"])
def checking(project: str) -> list:
	"""P3-75 (D-417): the client's own large sends to this project: "Checking…" while scanned, then a reason if refused
	(threat, could_not_check, not_stored); one that passed is a File and leaves the list."""
	_clients_only()
	if not portal.can_read_project(project):
		raise frappe.DoesNotExistError(_("Not found"))
	return scan_holds.checking(project, frappe.session.user)


@frappe.whitelist(methods=["POST"])
def open_thread(message: str) -> str:
	"""The client's thread on a message of the Client room (QR-2), opened on first use; a second click opens the same
	thread. Its replies go through the normal send. A message the client may not read answers "not found"."""
	_clients_only()
	return chat_api.lost_race_once(lambda: chat_rooms.client_thread(message))


@frappe.whitelist(methods=["POST"])
def send_file(project: str) -> dict:
	"""A client sends one file to the project team in Files (P3-07; D-140, D-158, D-159, D-179). A file in a
	conversation goes through the chat's own upload and send since P3-65 (discuss.parts.attachments; D-439's stopgap is
	gone). The checks run in this order, each in this body (DR-5), and the file's bytes are read only from step 5:
	1 the client, the project and its portal, and a burst limit; 2 Files is on; 4 the type; 5 the signature; 6 the size
	and the project's daily cap; 7 the structure; 8 the virus scan. The answer names the file by its name and address,
	never its id. P3-75 (D-417): a model file above the in-request scan budget is held and scanned by a background job,
	and the answer says it is being checked (scan_holds.hold)."""
	started = time.monotonic()
	frappe.form_dict.pop("file_size", None)  # File.validate would take it over the real size
	_clients_only()
	_check_project(project)
	client_files.check_burst(frappe.session.user)
	_check_files_on(project)
	request = getattr(frappe.local, "request", None)
	parts = list(request.files.items(multi=True)) if request is not None and request.files else []
	if len(parts) > 1 or (parts and parts[0][0] != "file"):
		frappe.throw(_("Choose one file to send"))
	if not parts:
		frappe.throw(_("Choose a file to send"))
	display, ext = client_files.clean_name(parts[0][1].filename)
	client_files.check_type(ext)
	limit = client_limit()
	content = parts[0][1].stream.read(limit + 1)  # the first read: never more than the limit into memory
	if not content:
		frappe.throw(_("The file is empty"))
	client_files.check_signature(ext, content)
	if len(content) > limit:
		frappe.throw(_("The file is larger than {0}").format(client_files.size_text(limit)))
	client_files.check_daily_cap(project, len(content))
	client_files.check_structure(ext, content)
	if len(content) > client_files.SCAN_IN_REQUEST:  # D-417: a large model file is scanned after the request (P3-75)
		from construction_core.discuss import media

		with media.slot(frappe.session.user), client_files.large_slot():  # two at a time per user, two on the site
			return scan_holds.hold(project, display, ext, content)
	# The scan gets what is left of the request's 120 s, keeping 10 s to store (P3-07 audit S2).
	client_files.scan(content, project=project, budget=max(5.0, 110.0 - (time.monotonic() - started)))
	return _store(project, display, content)


def _check_project(project) -> None:
	"""Step 1: the same answer for a missing, foreign or switched-off project."""
	if not (isinstance(project, str) and portal.can_read_project(project)):
		raise frappe.DoesNotExistError(_("Not found"))
	refuse_closed(project)  # P3-59 (T10): a closed project's client only reads


def _check_files_on(project: str) -> None:
	"""Step 2: Files is on."""
	if not client_section_open("File", project):
		frappe.throw(_("Sending files is switched off for this project"), frappe.PermissionError)


def _store(project: str, display: str, content: bytes) -> dict:
	"""Store the checked bytes at a path of their own in From client, seen by its sender and the team until shared
	(D-158), and tell the team."""
	folder = client_folders(project)["inbox"]
	if not folder:
		frappe.throw(_("This project cannot receive files yet. Ask the project team."))
	attach = ("Construction Project", project)
	# validate_file allows exactly this one insert, as described here (permissions.client_upload_shape).
	frappe.flags.cc_client_upload = frappe._dict(project=project, folder=folder, visible=0, attach=attach,
		consumed=False)
	try:
		name = get_storage().put_own(f"{root_path(project)}/{CLIENT_INBOX}", display, content, project,
			client_visible=False, attach=attach)
	except MaxFileSizeReachedError:
		frappe.throw(_("This image is too large to store once its hidden data is removed. Send a smaller copy."))
	finally:
		frappe.flags.cc_client_upload = False
	f = frappe.get_doc("File", name)
	notify(chat_api.staff_members(project), CLIENT_FILE, f, actor=frappe.session.user)
	return {"file_name": f.file_name, "url": f.file_url, "size": f.file_size, "shared": False}


def answer(view: dict, user: str | None = None, caller: str | None = None) -> dict:
	"""What leaves for a client (``user``; None: the session user): files without their id, and each thread's messages
	through the chat's one exit (discuss.view.respond), in the keys the portal reads. ``caller``: the staff preview's
	own user, whose reads also bound every message and card."""
	viewer = user or frappe.session.user
	for f in view["files"]:
		f.pop("_file", None)
	memo = {}
	for t in view["threads"]:
		kept = chat_view.respond({"messages": t["messages"]}, viewer, caller, memo)["messages"]
		t["messages"] = [_portal_message(m) for m in kept]
	return view


def _portal_message(m: dict) -> dict:
	"""Only what the page shows of each message, as it was before the core shape (P3-64 moves the page)."""
	legacy = chat_api.legacy_message(m)
	return {"name": m["name"], "author_name": frappe.utils.get_fullname(m["author"]["user"]), "when": m["when"],
		"text": m["text"], "attachment": legacy["attachment"], "mine": m["mine"]}
