"""A project's files for the workspace's Files section (P2-04, D-117).

Every read and write goes through ``get_storage()`` (DR-4) and checks permission in its own body (DR-5): the project
must be readable by the session user, each listed file is checked with ``has_permission``, and the writes run as the
user, so ``construction_core.permissions`` decides (DR-6). Staff only: clients read their files through the portal.
"""

import html
import json
import os
import re

import frappe
from frappe import _
from frappe.utils import cint, get_fullname
from frappe.utils.file_manager import get_max_file_size

from construction_core.client_files import type_limit
from construction_core.files import versions
from construction_core.permissions import is_client
from construction_core.providers.storage import CLIENT_CHAT, CLIENT_FOLDERS, CLIENT_INBOX, get_storage
from construction_core.workspace import root_path

CLIENT_FOLDER_KIND = {CLIENT_INBOX: "inbox", CLIENT_CHAT: "chat"}  # P3-07: where the files clients send land


def _staff_only():
	if is_client(frappe.session.user):
		frappe.throw(_("This is for the project team only"), frappe.PermissionError)


def _readable_project(project: str):
	"""The same answer for a project that does not exist and one the user may not read."""
	if not (project and frappe.db.exists("Construction Project", project)
			and frappe.has_permission("Construction Project", "read", doc=project)):
		raise frappe.DoesNotExistError(_("Project not found"))


def _folders(project: str) -> dict[str, str]:
	"""The project's folder tree, relative path -> folder id, as provisioned by workspace.create_workspace.

	The stored map names only the template's paths, so a parent such as 02_Design (of 02_Design/Drawings) was missing
	and the tree drew its children under the folder before it (P3-41). Each missing parent is added here from its
	child's own File.folder, so every project's tree is whole without a migration."""
	raw = frappe.db.get_value("Workspace Config", project, "folders")
	folders = json.loads(raw) if raw else {}
	for path in sorted(folders, key=lambda p: -p.count("/")):
		child, parts = path, path.split("/")
		for depth in range(len(parts) - 1, 0, -1):
			parent = "/".join(parts[:depth])
			if parent in folders:
				break
			fid = frappe.db.get_value("File", folders[child], "folder")
			# Only a folder of this project: one moved elsewhere in Desk must not bring another project's folder in.
			if not fid or frappe.db.get_value("File", fid, "cc_project") != project:
				break
			folders[parent] = fid
			child = parent
	return folders


def _folder_path(project: str, folder: str) -> str:
	for path, fid in _folders(project).items():
		if fid == folder:
			return path
	raise frappe.DoesNotExistError(_("Folder not found"))


def _project_file(file: str) -> str:
	"""The project of a file the user may read; the same answer for a missing, foreign or non-project file."""
	row = frappe.db.get_value("File", file, ["cc_project", "is_folder", "cc_version_of"], as_dict=True) if file else None
	# P3-43 (D-301): an earlier version is reached through its file's Versions tab, never as a file of its own
	readable = bool(row and row.cc_project and not row.is_folder and not row.cc_version_of
		and frappe.db.exists("Construction Project", row.cc_project)
		and frappe.has_permission("Construction Project", "read", doc=row.cc_project)
		and frappe.has_permission("File", "read", doc=file))
	if not readable:
		raise frappe.DoesNotExistError(_("File not found"))
	return row.cc_project


@frappe.whitelist(methods=["GET"])
def tree(project: str) -> list[dict]:
	_staff_only()
	_readable_project(project)
	folders = _folders(project)
	ids = list(folders.values()) or [""]
	flags = dict(frappe.get_all("File", filters={"name": ["in", ids]}, fields=["name", "cc_client_visible"], as_list=True))
	# P3-41: the files directly in each folder (not in the bin), for the tree's counts and the project's total
	counts = dict(frappe.db.sql("""select folder, count(*) from `tabFile`
		where folder in %(ids)s and is_folder = 0 and ifnull(cc_trashed, 0) = 0 and ifnull(cc_version_of, '') = ''
		group by folder""", {"ids": tuple(ids)}))
	return [
		{"path": path, "folder": fid, "label": path.rsplit("/", 1)[-1] if path else _("Project files"),
			"parent": path.rsplit("/", 1)[0] if "/" in path else ("" if path else None),
			"depth": path.count("/") + 1 if path else 0, "client_visible": cint(flags.get(fid)),
			"client_folder": CLIENT_FOLDER_KIND.get(path, ""), "count": cint(counts.get(fid))}
		for path, fid in sorted(folders.items())
	]


def _entries(rows: list[dict], folders: dict[str, str] | None = None) -> list[dict]:
	"""What the Files screen shows of each file: who owns it (a client's own file says so), and where it is."""
	where = {fid: path for path, fid in (folders or {}).items()}
	names = {}
	for e in rows:
		owner = e.get("owner")
		if owner not in names:
			names[owner] = get_fullname(owner)
		e["from_client"] = is_client(owner)
		e["sender"] = e["owner_name"] = names[owner]
		if folders is not None:
			e["path"] = where.get(e.get("folder"), "")
	return rows


@frappe.whitelist(methods=["GET"])
def list_files(project: str, folder: str) -> list[dict]:
	_staff_only()
	_readable_project(project)
	_folder_path(project, folder)
	rows = [e for e in get_storage().list_folder(folder)
		if not e["is_folder"] and frappe.has_permission("File", "read", doc=e["name"])]
	return _entries(rows)  # P3-07: a file a client sent says so, and who sent it


VIEWS = ("shared", "recent")
RECENT = 50


@frappe.whitelist(methods=["GET"])
def list_view(project: str, view: str) -> list[dict]:
	"""P3-41: the folder pane's shortcuts across the whole project: the files shared with its clients, or the newest."""
	_staff_only()
	_readable_project(project)
	if view not in VIEWS:
		raise frappe.DoesNotExistError(_("View not found"))
	folders = _folders(project)
	filters = {"cc_project": project, "is_folder": 0, "cc_trashed": ["in", [0, None]],
		"folder": ["in", list(folders.values()) or [""]], "cc_version_of": ["is", "not set"]}
	if view == "shared":
		filters["cc_client_visible"] = 1
	rows = frappe.get_all("File", filters=filters, order_by="modified desc", limit=RECENT if view == "recent" else 500,
		fields=["name", "file_name", "is_folder", "file_size", "modified", "owner", "cc_client_visible", "file_url", "folder",
			"cc_rev", "content_hash"])
	rows = [{"name": r.name, "file_name": r.file_name, "is_folder": 0, "file_size": r.file_size, "modified": r.modified,
		"owner": r.owner, "client_visible": r.cc_client_visible, "url": r.file_url, "folder": r.folder,
		"rev": r.cc_rev or "A", "content_hash": r.content_hash or ""}
		for r in rows if frappe.has_permission("File", "read", doc=r.name)]
	return _entries(rows, folders)


FOLDER_NAME = re.compile(r"^[^/\\:*?\"<>|\x00-\x1f\x7f\u200e\u200f\u202a-\u202e\u2066-\u2069]{1,80}$")


@frappe.whitelist(methods=["POST"])
def new_folder(project: str, parent: str, name: str) -> dict:
	"""P3-41: a folder inside one of the project's folders, kept in the project's folder map. The clients' folders
	take none (D-158): what a client sees there is decided file by file."""
	_staff_only()
	_readable_project(project)
	if not frappe.has_permission("Construction Project", "write", doc=project):
		frappe.throw(_("You cannot add folders to this project"), frappe.PermissionError)
	parent_path = _folder_path(project, parent)
	if parent_path == "06_Client" or parent_path.startswith("06_Client/"):
		frappe.throw(_("Folders are not added to the client's folder"), frappe.PermissionError)
	name = (name or "").strip()
	if not FOLDER_NAME.match(name) or name.startswith(".") or name in (".", ".."):
		frappe.throw(_("Use a folder name without / \\ : * ? \" < > |, at most 80 characters"))
	path = f"{parent_path}/{name}" if parent_path else name
	folders = _folders(project)
	if path in folders or frappe.db.exists("File", {"folder": parent, "file_name": name, "is_folder": 1}):
		frappe.throw(_("A folder with this name is already here"))
	fid = get_storage().ensure_path(f"{root_path(project)}/{path}", project)
	cfg = frappe.get_doc("Workspace Config", project)
	stored = json.loads(cfg.folders or "{}")
	stored.update({p: f for p, f in folders.items() if p not in stored})  # the parents _folders filled in
	stored[path] = fid
	cfg.folders = json.dumps(stored, sort_keys=True)
	cfg.flags.cc_system = True  # the folder map is server-set (WorkspaceConfig.validate)
	cfg.save(ignore_permissions=True)  # the user's right to the project was checked above
	return {"folder": fid, "path": path}


@frappe.whitelist(methods=["POST"])
def move(project: str, files: str | list, folder: str) -> dict:
	"""P3-41: put files in another folder of the same project. A file a client sent stays where the clients' rules
	keep it, and nothing is moved into the clients' folders (D-158)."""
	_staff_only()
	_readable_project(project)
	target = _folder_path(project, folder)
	if frappe.db.get_value("File", folder, ["cc_project", "is_folder"]) != (project, 1):
		raise frappe.DoesNotExistError(_("Folder not found"))  # a folder of this project only (P3-41 audit S1)
	if target in CLIENT_FOLDERS:
		frappe.throw(_("Only the project's clients add files to this folder"), frappe.PermissionError)
	names = json.loads(files) if isinstance(files, str) and files.startswith("[") else files
	names = [names] if isinstance(names, str) else list(names or [])
	if not names or len(names) > 200:
		frappe.throw(_("Choose between 1 and 200 files"))
	where = {fid: path for path, fid in _folders(project).items()}
	moved = []
	for name in names:
		if _project_file(name) != project or frappe.db.get_value("File", name, "cc_trashed"):
			raise frappe.DoesNotExistError(_("File not found"))
		row = frappe.db.get_value("File", name, ["owner", "folder"], as_dict=True)
		if is_client(row.owner) or where.get(row.folder, "") in CLIENT_FOLDERS:
			frappe.throw(_("A file a client sent stays in the client's folder"), frappe.PermissionError)
		if row.folder != folder:
			get_storage().move(name, folder)
			frappe.get_doc("File", name).add_comment("Info", _("Moved to {0}").format(target or _("Project files")))
		moved.append(name)
	return {"moved": moved, "path": target}


@frappe.whitelist(methods=["GET"])
def details(file: str) -> dict:
	"""P3-41: the side panel of one file: what it is, where, whose, who sees it, and what happened to it."""
	_staff_only()
	project = _project_file(file)
	f = frappe.get_doc("File", file)
	if f.cc_trashed:
		raise frappe.DoesNotExistError(_("File not found"))
	where = {fid: path for path, fid in _folders(project).items()}
	events = [{"who": get_fullname(f.owner), "what": _("added the file"), "when": f.creation}]
	for c in frappe.get_all("Comment", filters={"reference_doctype": "File", "reference_name": file,
			"comment_type": ["in", ["Info", "Comment", "Edit"]]}, fields=["owner", "content", "creation"],
			order_by="creation asc", limit=100):
		# text, as the panel shows it with {{ }}: our own lines are escaped HTML (versions.revise), so unescape them
		events.append({"who": get_fullname(c.owner), "what": html.unescape(frappe.utils.strip_html(c.content or "")),
			"when": c.creation})
	events.reverse()  # newest first
	history = versions.history(f)  # P3-43: every revision, newest first
	return {"name": f.name, "file_name": f.file_name, "file_size": f.file_size, "modified": f.modified,
		"creation": f.creation, "owner_name": get_fullname(f.owner), "from_client": is_client(f.owner),
		"client_visible": cint(f.cc_client_visible), "path": where.get(f.folder, ""), "url": f.file_url,
		"team": len({r.user for r in frappe.get_doc("Construction Project", project).users if not is_client(r.user)}),
		"events": events, "rev": history[0]["rev"], "versions": history, "content_hash": f.content_hash or "",
		"drawings": [{"name": d.name, "title": d.title, "takeoffs": d.takeoffs} for d in versions.drawings(f)],
		# D-306: a marked sign-in picture keeps the copy a manager approved until one marks the new revision
		"signin": bool(frappe.db.exists("Signin Picture", {"source_file": f.name, "enabled": 1})),
		# P3-48: why a new revision would be refused now ('' when it would not), so the viewer offers Edit only then
		"revisable": _why_not_revisable(f)}


def _why_not_revisable(f) -> str:
	"""versions.check_revisable's refusal as text, '' when a new revision may be made; nothing is queued for the user."""
	queued = len(frappe.local.message_log)
	try:
		versions.check_revisable(f)
	except (frappe.ValidationError, frappe.PermissionError) as e:  # DoesNotExistError is a ValidationError
		del frappe.local.message_log[queued:]  # only the refusal's own message; any queued before it stays
		return str(e) or _("You cannot change this file")
	return ""


# --- P3-43 (D-301, D-302, D-303): file versions ----------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def upload_version(file: str, note: str = "", takeoffs: str | None = None) -> dict:
	"""The request's file (multipart ``file``) becomes the file's next revision; its current content is kept as a
	version. Same type only; the file keeps its name, id and link (versions.revise)."""
	_staff_only()
	project = _project_file(file)
	f = frappe.get_doc("File", file)
	sent = frappe.request.files.get("file") if getattr(frappe, "request", None) else None
	if not sent or not os.path.basename(sent.filename or "").strip():
		frappe.throw(_("Choose a file to upload"))
	versions.same_type(f, os.path.basename(sent.filename))
	limit = min(type_limit(versions.split_name(f.file_name)[1].lstrip(".").lower()), get_max_file_size())  # D-417: 250 MB for a model file; never above the site's
	content = sent.stream.read(limit + 1)  # never more than the site's limit into memory (P2-04 audit 7)
	if len(content) > limit:
		size = f"{limit / 1048576:.1f} MB" if limit >= 1048576 else f"{limit // 1024} KB"
		frappe.throw(_("The file is larger than {0}").format(size))
	if not content:
		frappe.throw(_("The chosen file is empty"))
	content = versions.checked_content(f, content)
	out = _once_more(lambda: versions.revise(file, content, note=note, takeoffs=takeoffs,
		comment=_("Uploaded Rev {rev}: {note}") if versions.clean_note(note) else _("Uploaded Rev {rev}")))
	return {**out, "project": project}


def _once_more(revise):
	"""A revision made by someone else at the same moment fails this one with MariaDB 1020 (snapshot isolation, P3-43
	audit S3) and MariaDB rolls the request back: start again in a new transaction, where revise locks, reads afresh
	and checks again; then say so plainly."""
	try:
		return revise()
	except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
		frappe.db.rollback()
		try:
			return revise()
		except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
			frappe.db.rollback()
			frappe.throw(_("Someone changed this file just now. Please try again."))


@frappe.whitelist(methods=["POST"])
def restore(version: str, takeoffs: str | None = None) -> dict:
	"""An earlier version's content becomes the file's next revision; nothing is deleted (D-303)."""
	_staff_only()
	row = frappe.db.get_value("File", version, ["cc_version_of", "cc_rev"], as_dict=True) if version else None
	if not row or not row.cc_version_of:
		raise frappe.DoesNotExistError(_("Version not found"))
	project = _project_file(row.cc_version_of)
	v = frappe.get_doc("File", version)
	if v.cc_project != project or not frappe.has_permission("File", "read", doc=v):
		raise frappe.DoesNotExistError(_("Version not found"))
	content = versions.read_bytes(v)
	out = _once_more(lambda: versions.revise(row.cc_version_of, content, note=_("Restored from Rev {0}").format(row.cc_rev),
		takeoffs=takeoffs, comment=_("Restored Rev {old} as Rev {rev}").replace("{old}", row.cc_rev)))
	return {**out, "project": project}


@frappe.whitelist(methods=["POST"])
def upload(project: str, folder: str, client_visible: int | str = 0) -> dict:
	"""Store the request's file (multipart field ``file``) in one of the project's folders, as the session user."""
	_staff_only()
	_readable_project(project)
	path = _folder_path(project, folder)
	if path in CLIENT_FOLDERS:  # P3-07 (D-158); validate_file refuses it on every other route too
		frappe.throw(_("Only the project's clients add files to this folder"), frappe.PermissionError)
	sent = frappe.request.files.get("file") if getattr(frappe, "request", None) else None
	file_name = os.path.basename((sent.filename if sent else "") or "").strip()
	if not file_name or file_name.startswith("."):
		frappe.throw(_("Choose a file to upload"))
	limit = min(type_limit(file_name.rpartition(".")[2].lower() if "." in file_name else ""), get_max_file_size())  # D-417: 250 MB for a model file; never above the site's
	content = sent.stream.read(limit + 1)  # never more than the site's limit into memory (P2-04 audit 7)
	if len(content) > limit:
		size = f"{limit / 1048576:.1f} MB" if limit >= 1048576 else f"{limit // 1024} KB"
		frappe.throw(_("The file is larger than {0}").format(size))
	full = f"{root_path(project)}/{path}" if path else root_path(project)
	name = get_storage().put(full, file_name, content, project=project, client_visible=bool(cint(client_visible)))
	return {"name": name}


@frappe.whitelist(methods=["POST"])
def set_client_visible(file: str, visible: int | str) -> None:
	_staff_only()
	_project_file(file)
	now = bool(cint(visible))
	if bool(frappe.db.get_value("File", file, "cc_client_visible")) != now:
		get_storage().set_client_visible(file, now)  # File.save: write permission, staff only (DR-6)
		frappe.get_doc("File", file).add_comment("Info", _("Shared with the client") if now else _("Stopped sharing with the client"))


@frappe.whitelist(methods=["POST"])
def trash(file: str) -> None:
	"""Trash, never delete (StorageProvider.delete): the file leaves every listing and stays recoverable."""
	_staff_only()
	_project_file(file)
	get_storage().delete(file)  # checks write permission
