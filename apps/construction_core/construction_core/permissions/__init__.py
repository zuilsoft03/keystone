"""Project-scoped access: the access boundary of DR-6 (ARCHITECTURE §2.1-§2.3).

Rules that the code below depends on (measured on Frappe v16.50.0, P1-02 and its audit):
- A ``has_permission`` hook can only deny, and **any falsy return denies, including None**
  (``frappe/permissions.py: has_controller_permissions``). So "no objection" is ``True``, never ``None``.
- ``permission_query_conditions`` are ANDed with Frappe's own (File has its own: a non-System User sees only
  files they own), **but a DocShare is ORed around them** (``frappe/database/query.py``) and overrides a hook
  denial in ``has_permission``. So a share to a non-member is refused at the DocShare itself (``validate_share``).
- File downloads call ``File.is_downloadable``, which bypasses app hooks; ``overrides.file`` closes that.
- A User Permission only narrows a role that already grants read; removing one restores what the role grants
  (S12b, D-052). The default deny below is what isolates clients and removed members.
"""

from contextlib import contextmanager

import frappe
from frappe import _

from construction_core.approvals import read as approvals_read
from construction_core.providers.storage import PROJECTS_ROOT, ROOT

CLIENT_ROLE = "Construction Client"

# The project field per doctype (D-086). A File or Task that belongs to no project keeps Frappe's own
# permission (it passes through these predicates), so ERPNext records outside projects are unaffected (D-091).
PROJECT_FIELD = {"Construction Project": "name", "File": "cc_project"}
PASS_THROUGH_WHEN_EMPTY = {"File", "Construction Task"}
SCOPED_DOCTYPES = (
	"Construction Project", "Construction Task", "File", "Workspace Config", "Project Document", "BOQ", "WBS Node",
	"RFI", "Submittal", "Variation Order", "Discuss Thread", "Discuss Message", "Discuss Anchor", "Discuss Read State",
	"Discuss Pointer", "Discuss Follow", "Whiteboard", "Whiteboard Version", "CAD Drawing", "Takeoff",
	"Discuss Attachment", "Discuss Ref", "Discuss Poll", "Discuss Poll Vote", "Discuss Reaction", "Discuss Message Version",
	"Discuss Removed Text", "File Request", "Approval Request", "Approval Event", "Approval Evidence Detail",
	"Client Decision",  # P3-77 (§7): staff-only; a client sees a Decision only through its request
)  # each slice adds the doctypes it creates (DR-6)
# What a client (Website User) may read (D-087). A share never gives a client more than this.
CLIENT_READABLE = {
	"Construction Project", "File", "Project Document", "RFI", "Submittal", "Variation Order", "Discuss Thread", "Discuss Message",
	"Whiteboard", "Approval Request",  # Approval Request: through its own rule only (approvals.read, P3-76)
}
# The approvals ledger (P3-76, D-428): shared with no one, a System Manager neither; a client reads a request only
# through its rule, and a share is ORed around that rule.
APPROVAL_DOCTYPES = frozenset({"Approval Request", "Approval Event", "Approval Evidence Detail"})
# Extra rules for clients, per doctype: SQL for lists, and a matching check for one document.
CLIENT_ONLY_SQL = {
	"File": "`tabFile`.`cc_client_visible` = 1 and ifnull(`tabFile`.`cc_trashed`, 0) = 0",
	"Project Document": "`tabProject Document`.`client_visible` = 1 and `tabProject Document`.`status` = 'Published'",
	"RFI": "`tabRFI`.`client_visible` = 1 and `tabRFI`.`status` != 'Draft'",
	"Submittal": "`tabSubmittal`.`client_visible` = 1 and `tabSubmittal`.`status` != 'Draft'",
	"Variation Order": "`tabVariation Order`.`client_visible` = 1 and `tabVariation Order`.`stage` != 'Potential Change'",
	"Discuss Thread": "`tabDiscuss Thread`.`audience` = 'Client'",
	"Discuss Message": "`tabDiscuss Message`.`audience` = 'Client' and ifnull(`tabDiscuss Message`.`staff_only`, 0) = 0",
	"Whiteboard": "`tabWhiteboard`.`client_visible` = 1",
	"Approval Request": approvals_read.CLIENT_SQL,  # not Draft, decided by the client; never the subject's (§7)
}
# The portal sections the team switches on or off per project (D-098), by doctype. A switched-off section is
# refused to clients here, not only hidden by the portal page. Workspace Config rows; a missing row means on.
CLIENT_SECTION = {
	"File": "files", "Project Document": "documents", "RFI": "rfi", "Submittal": "submittals",
	"Variation Order": "variations", "Discuss Thread": "discuss", "Discuss Message": "discuss",
	"Whiteboard": "whiteboards", "Approval Request": "approvals",
}
# A section that starts off for clients: on only where its row says so, so a project without the row (an existing one,
# or one without a workspace) keeps it off (P3-76; its switch is P3-77's).
DEFAULT_OFF = frozenset({"approvals"})
CLIENT_HIDDEN_STATE = {"RFI": ("status", "Draft"), "Submittal": ("status", "Draft"), "Variation Order": ("stage", "Potential Change")}
# What a client may never do to a project File on their own (P3-02): they read what is shared, and they add a file only
# through the portal's upload endpoint (P3-07), never by a write of their own through Frappe's File calls.
CLIENT_FILE_WRITES = {"write", "create", "delete", "share", "submit", "cancel", "amend"}
# Where project files live: Home/Projects/<project>/... (workspace.root_path, providers.storage). A storage provider
# that keeps its own folders marks them with cc_project, which in_project_area also reads.
PROJECT_FOLDERS = f"{ROOT}/{PROJECTS_ROOT}"
# The child tables of our records (P2-04 audit 1-2). Their rows change only through their record's save.
CHILD_DOCTYPES = (
	"Attachment Ref", "BOQ Line", "Distribution User", "Folder Template Item", "Project Member", "Submittal Revision",
	"Takeoff Item", "VO BOQ Delta", "Workspace Section", "File Request Item", "File Request Recipient",
	"Client Decision Option",
)


def client_may_see(doc) -> bool:
	if doc.doctype == "File":
		return bool(doc.get("cc_client_visible")) and not doc.get("cc_trashed")
	if doc.doctype == "Project Document":
		return bool(doc.get("client_visible")) and doc.get("status") == "Published"
	if doc.doctype in CLIENT_HIDDEN_STATE:
		field, hidden = CLIENT_HIDDEN_STATE[doc.doctype]
		return bool(doc.get("client_visible")) and doc.get(field) != hidden
	if doc.doctype == "Discuss Thread":
		return doc.get("audience") == "Client"
	if doc.doctype == "Whiteboard":
		return bool(doc.get("client_visible"))
	if doc.doctype == "Discuss Message":
		return _thread_of(doc)[1] == "Client" and not doc.get("staff_only")  # staff notes never reach a client
	if doc.doctype == "Approval Request":
		return approvals_read.client_may_read(doc)
	return doc.doctype in CLIENT_READABLE


@contextmanager
def switches_once():
	"""Within one chat read, each project's portal and section switches are read once: a page asks them for every
	list and every record it reads as a client, and they do not change in the middle of one read (P3-73). Nothing is
	kept after the block. For a client's session the first switch asked reads them for all of the client's projects at
	once, two queries in all, so a read across their projects (the inbox, P3-74) costs the same for one or many."""
	if getattr(frappe.local, "cc_switches", None) is not None:
		yield
		return
	frappe.local.cc_switches = {}
	try:
		yield
	finally:
		frappe.local.cc_switches = None


def _switch(key, read):
	memo = getattr(frappe.local, "cc_switches", None)
	if memo is None:
		return read()
	if key not in memo and not memo.get("primed"):
		memo["primed"] = True
		user = frappe.session.user
		if is_client(user):
			_prime(memo, allowed_projects(user))
	if key not in memo:
		memo[key] = read()
	return memo[key]


def _prime(memo: dict, projects: list[str]) -> None:
	"""The portal and section switches of ``projects``, in the shapes the single reads keep: the stored portal value
	(None without a config row) and the set of sections off."""
	if not projects:
		return
	configs = frappe.get_all("Workspace Config", filters={"name": ["in", projects]},
		fields=["name", "client_portal_enabled", "archived"], as_list=True)
	portal = {name: on for name, on, _archived in configs}
	closed = {name for name, _on, archived in configs if archived}
	rows = {}
	for parent, section, visible in frappe.get_all("Workspace Section", filters={"parenttype": "Workspace Config",
			"parent": ["in", projects]}, fields=["parent", "section", "client_visible"], as_list=True):
		rows.setdefault(parent, []).append((section, visible))
	for p in projects:
		memo[("portal", p)] = portal.get(p)
		memo[("sections", p)] = _sections_off(rows.get(p, ()))
		memo[("closed", p)] = p in closed


def _sections_off(rows) -> set[str]:
	"""The sections a row switches off for clients, and each DEFAULT_OFF section no row switches on."""
	return {s for s, visible in rows if not visible} | (DEFAULT_OFF - {s for s, visible in rows if visible})


def client_sections_off(project: str) -> set[str]:
	return _switch(("sections", project), lambda: _sections_off(frappe.get_all("Workspace Section", filters={
		"parenttype": "Workspace Config", "parent": project}, fields=["section", "client_visible"], as_list=True)))


def client_section_open(doctype: str, project: str | None) -> bool:
	section = CLIENT_SECTION.get(doctype)
	return not section or not project or section not in client_sections_off(project)


def client_portal_open(project: str | None) -> bool:
	"""Workspace Config "Client Portal Enabled" (default on; no config means on). Off, the project's clients see
	nothing of it: the project, its records and its files, here at the access boundary (P2-04, D-117)."""
	if not project:
		return True
	value = _switch(("portal", project), lambda: frappe.db.get_value("Workspace Config", project,
		"client_portal_enabled"))
	return value is None or bool(frappe.utils.cint(value))


def project_closed(project: str | None) -> bool:
	"""P3-59 (QG, D-338): Close project archived the project's Workspace Config. Its chat takes no new write from anyone,
	and its clients only read (T10)."""
	if not project:
		return False
	return _switch(("closed", project), lambda: bool(frappe.utils.cint(frappe.db.get_value("Workspace Config", project,
		"archived"))))


class ProjectClosedError(frappe.ValidationError):
	http_status_code = 403  # not a PermissionError: callers that answer those as "not found" let this one through


def refuse_closed(project: str | None) -> None:
	if project_closed(project):
		frappe.throw(_("This project is closed. You can still read it."), ProjectClosedError)


BYPASS_ROLES = {"System Manager"}


def _bypass(user: str) -> bool:
	return user == "Administrator" or bool(BYPASS_ROLES & set(frappe.get_roles(user)))


def is_client(user: str) -> bool:
	return frappe.get_cached_value("User", user, "user_type") == "Website User"


def allowed_projects(user: str) -> list[str]:
	"""Projects the user is a member of, from the User Permission rows the §2.3 sync writes. Cached by Frappe."""
	return [p["doc"] for p in frappe.permissions.get_user_permissions(user).get("Construction Project") or []]


def is_member(user: str, project: str) -> bool:
	"""Membership straight from the Project's members table (the source the sync copies from)."""
	return bool(frappe.db.exists("Project Member", {"parenttype": "Construction Project", "parent": project, "user": user}))


def project_field(doctype: str) -> str:
	return PROJECT_FIELD.get(doctype, "project")


def project_of(doc) -> str | None:
	if doc.doctype == "Discuss Message":
		return _thread_of(doc)[0]
	if doc.doctype == "Discuss Thread" and doc.get("anchor_doctype") and doc.get("anchor_name"):
		return anchor_project(doc.anchor_doctype, doc.anchor_name)
	if doc.doctype == "Takeoff" and doc.get("drawing"):
		return frappe.db.get_value("CAD Drawing", doc.drawing, "project")  # set in validate, after the create check
	if doc.doctype == "File" and not doc.get("cc_project") and doc.get("attached_to_doctype") == "Construction Project":
		return doc.get("attached_to_name")  # P3-46 (D-308): a Desk attachment on the project form is its internal file
	return doc.get(project_field(doc.doctype))


def anchor_project(doctype: str, name: str) -> str | None:
	"""The project of a record a thread is anchored to. Only project records anchor threads; the anchor is
	immutable, so this is also the thread's stored project. Frappe checks ``create`` before ``validate`` sets it."""
	if doctype == "Construction Project":
		return name if frappe.db.exists("Construction Project", name) else None
	if doctype not in SCOPED_DOCTYPES or frappe.get_meta(doctype).istable:
		return None
	return frappe.db.get_value(doctype, name, project_field(doctype))


def _thread_of(message) -> tuple:
	"""A message's project and audience are its thread's (both immutable). Frappe checks ``create`` before
	``before_insert`` copies them, so the check reads the thread rather than values the caller supplied."""
	if not message.get("thread"):
		return (None, None)
	return frappe.get_cached_value("Discuss Thread", message.thread, ["project", "audience"]) or (None, None)


def project_scoped(user: str | None = None, doctype: str | None = None) -> str:
	"""SQL condition for ``permission_query_conditions``: rows of the user's projects only (default deny)."""
	user = user or frappe.session.user
	if _bypass(user):
		return ""

	col = f"`tab{doctype}`.`{project_field(doctype)}`"
	unscoped = f"ifnull({col}, '') = ''" if doctype in PASS_THROUGH_WHEN_EMPTY else None

	allowed = allowed_projects(user)
	if allowed and is_client(user):
		allowed = [p for p in allowed if client_portal_open(p)]  # D-117: the project's portal switch
		if doctype in CLIENT_SECTION:
			allowed = [p for p in allowed if client_section_open(doctype, p)]  # D-098 section switches
	if not allowed:
		return _no_versions(doctype, unscoped or "1=0")

	names = ", ".join(frappe.db.escape(p) for p in allowed)
	scoped = f"{col} in ({names})"
	if doctype in CLIENT_ONLY_SQL and is_client(user):
		only = CLIENT_ONLY_SQL[doctype]
		if doctype == "File":  # P3-07 (D-158): a client also lists the files they sent, until trashed
			only = (f"({only} or (`tabFile`.`owner` = {frappe.db.escape(user)}"
				" and ifnull(`tabFile`.`cc_trashed`, 0) = 0))")
		scoped = f"({scoped} and {only})"  # §2.5
	if doctype == "Discuss Follow":  # P3-68 audit M1: per-person state (who was mentioned when): the person's own
		scoped = f"({scoped} and `tabDiscuss Follow`.`user` = {frappe.db.escape(user)})"
	if doctype == "Discuss Attachment":  # P3-65 (SEC-4): a waiting file is its uploader's alone (can_access too)
		scoped = (f"({scoped} and (`tabDiscuss Attachment`.`state` = 'Sent'"
			f" or `tabDiscuss Attachment`.`uploader` = {frappe.db.escape(user)}))")
	return _no_versions(doctype, f"({scoped} or {unscoped})" if unscoped else scoped)


def _no_versions(doctype: str | None, condition: str) -> str:
	"""P3-43 (D-305): a file's earlier versions leave Frappe's own lists (Desk's folders and Library, link search,
	REST lists) for everyone but System Managers; the team opens them from the file's Versions tab."""
	return f"({condition}) and ifnull(`tabFile`.`cc_version_of`, '') = ''" if doctype == "File" else condition


def can_access(doc, ptype: str | None = None, user: str | None = None, debug: bool = False) -> bool:
	"""``has_permission`` hook: deny a record of a project the user is not a member of. True means no objection."""
	user = user or frappe.session.user
	if _bypass(user):
		return True
	if doc.doctype == "Construction Project" and (not doc.name or not frappe.db.exists("Construction Project", doc.name)):
		# Creating a project: role permissions decide; the creator becomes a member (D-091). In v16 a doc built
		# with frappe.get_doc({...}) has no name yet and is_new() is False, so existence is checked instead.
		return True
	if is_client(user) and doc.doctype == "File" and doc.get("cc_version_of"):
		return False  # P3-43 (D-301): an earlier version of a file is the team's only, whatever else it says
	if doc.doctype == "File" and not doc.get("cc_project") and referenced_files(doc):
		# P3-46 (D-311): a reference follows its file wherever it is attached, the project form too (review finding 1)
		return opens_as_its_file(doc, ptype, user)
	project = project_of(doc)
	if not project and doc.doctype in PASS_THROUGH_WHEN_EMPTY:
		return True  # no objection: Frappe's own permission decides (D-086, D-091)
	if project not in allowed_projects(user):
		# On a Project itself, its own members table is the source the sync copies from; it is already true
		# while ERPNext's Project.on_update shares the project, before our sync has written the User Permission.
		if not (doc.doctype == "Construction Project" and user in {row.user for row in doc.get("users") or []}):
			return False
	if doc.doctype == "Discuss Attachment" and doc.get("state") != "Sent" and doc.get("uploader") != user:
		return False  # P3-65 (§3.2, SEC-4): a file waiting to be sent is its uploader's alone until the send
	if doc.doctype == "Discuss Follow" and doc.get("user") != user:
		return False  # P3-68 audit M1: a follow (and its mention time) is its person's own
	if doc.doctype == "File" and doc.get("cc_trashed") and binned_chat_file(doc.get("name")):
		return False  # P3-68 audit S1: a removed message's file is served to no one but a System Manager
	if doc.doctype == "File" and ptype == "delete" and (doc.get("cc_version_of") or (doc.get("name")
			and frappe.db.exists("File", {"cc_version_of": doc.name}))):
		return False  # P3-43 audit S1, S2: a file's history goes only with the file, by a System Manager
	# P3-07 (D-158): a client also reads a project file they sent themselves, until it is trashed, while they are a
	# member and the portal and the section are on. Shared or not, nobody else's.
	own = doc.doctype == "File" and doc.get("owner") == user and not doc.get("cc_trashed")
	if is_client(user) and not (client_portal_open(project) and (client_may_see(doc) or own)
			and client_section_open(doc.doctype, project)):
		return False
	if is_client(user) and (ptype or "read") in CLIENT_FILE_WRITES and project_closed(project):
		return False  # P3-59 (T10): after close a client only reads, whatever a role or a share would give
	if (is_client(user) and doc.doctype == "File" and (ptype or "read") in CLIENT_FILE_WRITES
			and not (ptype == "create" and client_upload())):
		return False  # P3-02: a client changes no project file; P3-07's endpoint only creates one
	return True


def binned_chat_file(name: str | None) -> bool:
	"""A file the chat made (an upload or a checked copy) that is in the bin: its message was removed (P3-68). Asked
	only for a binned file, so a page of live files costs no query."""
	from construction_core.discuss import media

	return media.chat_made(name)


def client_upload() -> bool:
	"""Whether this request is the portal's own upload endpoint (P3-07), which sets ``frappe.flags.cc_client_upload``
	around its save. ``frappe.flags`` is request-local, and no request payload reaches it."""
	return bool(frappe.flags.cc_client_upload)


def client_upload_shape() -> frappe._dict | None:
	"""The one File ``send_file`` or a chat send (discuss.media.materialize, P3-65, D-390) is about to store: its
	project, folder, visibility and attachment (P3-07). Only a dict describes one; validate_file allows exactly that
	insert, once, for the client or the staff member who sends it."""
	shape = frappe.flags.cc_client_upload
	return shape if isinstance(shape, dict) else None


def _claimed_file(doc, shape, user: str) -> None:
	"""The File matches the shape its caller described, exactly and once, or it is refused."""
	if (shape.consumed or doc.cc_project != shape.project or doc.folder != shape.folder
			or int(doc.cc_client_visible or 0) != shape.visible or doc.is_folder or not doc.is_private
			or (doc.attached_to_doctype, doc.attached_to_name) != tuple(shape.attach)
			or not is_member(user, shape.project)):
		frappe.throw(_("This file cannot be saved here"), frappe.PermissionError)
	shape.consumed = True


def in_project_area(doc) -> bool:
	"""Whether a File sits in a project's folders or is attached to a project record, whatever its cc_project says."""
	folder = doc.get("folder") or ""
	if folder == PROJECT_FOLDERS or folder.startswith(PROJECT_FOLDERS + "/"):
		return True
	if folder and frappe.db.get_value("File", folder, "cc_project"):
		return True
	attached = doc.get("attached_to_doctype")
	return bool(attached and (attached == "Construction Project" or attached in SCOPED_DOCTYPES))


def referenced_files(doc) -> list:
	"""The project files whose stored file a File row points at (P3-46): a Desk Library attach, a typed address."""
	if not doc.get("file_url") or doc.get("is_folder"):
		return []
	names = frappe.get_all("File", filters={"file_url": doc.file_url, "name": ["!=", doc.name or ""],
		"cc_project": ["is", "set"]}, pluck="name")
	return [frappe.get_doc("File", name) for name in names]


def opens_as_its_file(doc, ptype: str | None, user: str) -> bool:
	"""P3-46 (D-308): a File with no project on a project file's address is a reference to that file. A download is
	allowed when any row with the address is downloadable, so it opens only for those who may download the file
	itself (Frappe's File rule and ours, as ``is_downloadable`` asks), and a client changes none. Earlier versions too."""
	from frappe.core.doctype.file.file import has_permission as file_rule

	files = referenced_files(doc)
	if not any(file_rule(f, "read", user=user) and can_access(f, "read", user) for f in files):
		return False
	return not (is_client(user) and (ptype or "read") in CLIENT_FILE_WRITES)


def guard_shared_address(doc, before):
	"""P3-46 (D-310): a row on an address that other projects' files, an earlier version or an internal file hold
	gains no project and no client visibility past them. A reference named with a project and shared, or a Library
	copy given the project and then shared, would open the file under rules of its own. An upload Frappe stored on
	an existing address because its bytes are the same (``flags.cc_upload``) is a file of its own; system rows
	(``flags.cc_system``) are files.versions'."""
	new = before is None
	if doc.is_folder or not doc.file_url or doc.flags.cc_system or (new and doc.flags.cc_upload):
		return
	gains_project = bool(doc.cc_project) and (new or doc.cc_project != before.cc_project)
	gains_visibility = bool(frappe.utils.cint(doc.cc_client_visible)) and (new or not frappe.utils.cint(before.cc_client_visible))
	if not (gains_project or gains_visibility):
		return
	held = frappe.get_all("File", filters={"file_url": doc.file_url, "name": ["!=", doc.name or ""], "cc_project": ["is", "set"]},
		fields=["cc_project", "cc_client_visible", "cc_version_of"])
	if gains_project and any(row.cc_project != doc.cc_project for row in held):
		frappe.throw(_("This file belongs to another project"), frappe.PermissionError)
	if gains_visibility and any(row.cc_version_of or (row.cc_project == doc.cc_project and not row.cc_client_visible)
			for row in held):
		frappe.throw(_("Share the file this one comes from instead"), frappe.PermissionError)


def shares_project_bytes(doc) -> bool:
	"""Whether another File row points at the same stored file as a project's File. A download is allowed when any
	row with its address is downloadable, so a row of one's own on a project file's address would outlive every
	revocation of the project's own row (P3-02 audit)."""
	if not doc.get("file_url"):
		return False
	rows = frappe.get_all("File", filters={"file_url": doc.file_url, "name": ["!=", doc.name or ""]},
		fields=["cc_project", "folder", "attached_to_doctype"])
	return any(row.cc_project or in_project_area(row) for row in rows)


# permission_query_conditions hooks receive (user, doctype=...) in v16; one entry point serves every doctype.
def query_conditions(user: str | None = None, doctype: str | None = None) -> str:
	return project_scoped(user, doctype)



# --- write-side guards ------------------------------------------------------------------------------------


def in_setup() -> bool:
	"""Install, migrate, a patch or uninstall: Frappe's own setup paths, which the write-side guards let through."""
	return bool(frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch or frappe.flags.in_uninstall)


RENAME_CHECKED = "cc_rename_checked"


def mark_checked_rename(doc, method=None, *args):
	"""before_rename of every doctype (bypass-7): rename_doc runs it only when it runs its checks (validate_rename: write
	on the record and the doctype's allow_rename). The mark rides on the record's ``_local``, which rename_doc copies to
	the renamed record for after_rename in that case only."""
	doc._local = {**(getattr(doc, "_local", None) or {}), RENAME_CHECKED: True}


def refuse_unchecked_rename(doc, method=None, *args):
	"""after_rename of every doctype (bypass-7): Document.rename is whitelisted with ``validate_rename``, so anyone who
	reads a record (v1's run_doc_method, the v1 and v2 document method routes) could rename it with no check and no
	before_rename hook, a client their own sign-in address included. A rename without the mark is refused, and the throw
	rolls the request back. A DocType's own after_rename commits its table's rename before this runs.
	Both: overrides.rename refuses before any work where it extends a doctype; this backstops the rest and rename_doc."""
	# pop the mark: a reused object cannot pass a second unchecked rename on a stale _local (round 4, N-mark)
	checked = (getattr(doc, "_local", None) or {}).pop(RENAME_CHECKED, None)
	if not checked and not in_setup():
		frappe.throw(_("A rename that skips its checks is refused"), frappe.PermissionError)


def refuse_direct_child_write(doc, method=None):
	"""before_validate and on_trash of CHILD_DOCTYPES (P2-04 audit 1-2).

	Frappe's REST endpoints (/api/resource/<child>, /api/v2/document/<child>) save or delete a row on its own, then
	save its parent; the parent's controller then compares against the row already written and sees no change, so a
	submittal's review outcome or an approved BOQ's line could be changed past its rules. A record's own save runs
	its own hooks, never its rows' hooks, and deletes its removed rows directly, so this fires only for a row written
	or deleted on its own."""
	frappe.throw(_("Change {0} rows through their record").format(_(doc.doctype)), frappe.PermissionError)


def refuse_foreign_rows(doc, method=None):
	"""before_validate on every scoped doctype: a save must not take over another record's child rows.

	Frappe updates a child row by name without checking its current parent, so a save that names a row of another
	document moves it, out of an approved BOQ or across projects (P1-08 re-audit). Rows are matched by name,
	parent, parenttype and parentfield; a row whose name exists elsewhere is refused."""
	for df in doc.meta.get_table_fields():
		rows = [r for r in doc.get(df.fieldname) or [] if r.name]
		if not rows:
			continue
		found = frappe.get_all(df.options, filters={"name": ["in", [r.name for r in rows]]},
			fields=["name", "parent", "parenttype", "parentfield"])
		for row in found:
			if (row.parent, row.parenttype, row.parentfield) != (doc.name, doc.doctype, df.fieldname):
				frappe.throw(_("Row {0} belongs to another record").format(row.name), frappe.PermissionError)


def force_private(doc, method=None):
	"""File.before_validate: a project file is always private; a public URL would bypass every check (audit 7).
	Runs before File.validate, which decides where the content is stored from is_private."""
	if doc.cc_project:
		doc.is_private = 1


VERSION_FIELDS = ("cc_version_of", "cc_rev", "cc_rev_by", "cc_rev_on", "cc_rev_note")
# What else stays as the system wrote it on a version row (P3-43 review: clearing its project, or making it public,
# would put an earlier version where Frappe's own rules, not the project's, decide who reads it).
VERSION_FROZEN = ("cc_project", "is_private", "file_url", "attached_to_doctype", "attached_to_name", "folder")
CHAT_FROZEN = ("file_url", "file_name", "content_hash")  # a sent chat file's (P3-67 audit S4)


def guard_version_fields(doc):
	"""P3-43 (D-301, D-305): a file's revision fields are written by files.versions only (``flags.cc_system``), for
	every user; a version row keeps its project, privacy, address, attachment and folder; and it is never client
	visible."""
	if not doc.flags.cc_system:
		before = doc.get_doc_before_save() if not doc.is_new() else None
		if before is None and not (doc.is_new() or doc.flags.in_insert):
			before = frappe._dict(frappe.db.get_value("File", doc.name, VERSION_FIELDS + VERSION_FROZEN, as_dict=True) or {})
		changed = (any(doc.get(f) for f in VERSION_FIELDS) if before is None
			else any(str(before.get(f) or "") != str(doc.get(f) or "") for f in VERSION_FIELDS))
		if not changed and before is not None and before.get("cc_version_of"):
			changed = any(str(before.get(f) or "") != str(doc.get(f) or "") for f in VERSION_FROZEN)
		if changed:
			frappe.throw(_("A file's revisions are kept by the system"), frappe.PermissionError)
	if doc.get("cc_version_of") and frappe.utils.cint(doc.get("cc_client_visible")):
		frappe.throw(_("An earlier version of a file is never shared with clients"), frappe.PermissionError)


def validate_file(doc, method=None):
	"""File.validate: keep a project file in its project and keep client visibility a staff decision."""
	guard_version_fields(doc)
	user = frappe.session.user
	if _bypass(user):
		return
	before = doc.get_doc_before_save() if not doc.is_new() else None
	if before and not doc.flags.cc_system and any(str(before.get(f) or "") != str(doc.get(f) or "")
			for f in CHAT_FROZEN):
		from construction_core.discuss import media

		media.refuse_chat_made(doc.name)  # P3-67 audit S4: a sent chat file keeps the address, name and bytes it was checked as
	old_project = before.cc_project if before else None
	if old_project and not doc.cc_project:
		# P3-46 (D-308): with no project, Frappe's own rule (the record it is attached to) would decide who reads it.
		frappe.throw(_("Only a System Manager can take a file out of its project"), frappe.PermissionError)
	guard_shared_address(doc, before)
	if (old_project or None) != (doc.cc_project or None):
		for project in (old_project, doc.cc_project):
			if project and not is_member(user, project):
				frappe.throw(_("You are not a member of project {0}").format(project), frappe.PermissionError)
	new = bool(doc.flags.in_insert) or doc.is_new()
	if is_client(user):
		shape = client_upload_shape()
		if new and doc.cc_project and shape is not None:
			_claimed_file(doc, shape, user)  # P3-07: send_file stores exactly the one file it checked, as described, once
		else:
			was_visible = bool(before.cc_client_visible) if before else False
			if bool(doc.cc_client_visible) != was_visible:
				frappe.throw(_("Only project staff can change client visibility"), frappe.PermissionError)
			if new and doc.cc_project:  # a client adds a project file only through send_file (P3-07)
				frappe.throw(_("Files of a project are added by its team"), frappe.PermissionError)
			# P3-02: a File with no project passes through the predicate (D-086), so a client could otherwise file one
			# into a project's folders, or attach one to a project record, where the team takes it for the project's own.
			if not doc.cc_project and in_project_area(doc):
				frappe.throw(_("Files of a project are added by its team"), frappe.PermissionError)
		# A client's own row may not point at a project file's stored bytes (a library_file_name upload, a copied
		# file_url): it would keep the file after the team takes it away. An upload has an address of its own (P3-46).
		# Under send_file too: its own new path shares bytes with nothing, so this only ever refuses a forged row.
		if (new or doc.has_value_changed("file_url")) and shares_project_bytes(doc):
			frappe.throw(_("This file cannot be saved here"), frappe.PermissionError)  # names no project (audit note)
	elif new and doc.cc_project and client_upload_shape() is not None:
		# P3-65 (D-390, amending D-158): a chat send stores exactly the file its claim describes, in the client folder
		# for a Client conversation (a checked file), once. Nothing else of the team's reaches that folder.
		_claimed_file(doc, client_upload_shape(), user)
	elif doc.folder and (new or doc.has_value_changed("folder")):
		from construction_core.workspace import client_folders

		project = doc.cc_project or frappe.db.get_value("File", doc.folder, "cc_project")  # a Desk upload has none
		if project and doc.folder in client_folders(project).values():  # P3-07 (D-158): the clients' own folders
			frappe.throw(_("Only the project's clients add files to this folder"), frappe.PermissionError)


def revoke_foreign_shares(doc, method=None):
	"""Task/File.on_update: when a record's project is set or changed, shares held by everyone or by
	non-members are revoked; a share made before the record was scoped must not survive scoping (audit R2-2)."""
	project = project_of(doc)
	if not project or not doc.has_value_changed(project_field(doc.doctype)):
		return
	delete_shares(doc.doctype, doc.name, keep=lambda row: not row.everyone and is_member(row.user, project))


def revoke_member_shares(project: str, user: str):
	"""A removed member loses the shares they held on the project's records (audit R3)."""
	for doctype in SCOPED_DOCTYPES:
		if doctype in APPROVAL_DOCTYPES:
			continue  # never shared (validate_share), and a chain's rows would cost a query each
		if doctype == "Construction Project":
			names = [project]
		else:
			names = frappe.get_all(doctype, filters={project_field(doctype): project}, pluck="name")
		for name in names:
			delete_shares(doctype, name, keep=lambda row: row.user != user)


# Revoking is a rule of membership and of the project's switches, not the acting user's share right: DocShare.on_trash
# otherwise checks that the user may share the record, and a manager has no Share right on, e.g., Discuss Thread or
# File, so removing a client or switching the portal off would fail (P2-04 re-audit).
REVOKE = {"ignore_share_permission": True}  # passed as a copy: delete_doc adds keys to the dict it is given


def delete_shares(doctype: str, name: str, keep):
	"""Delete DocShare rows directly. frappe.share.remove() deletes with a permission check and matches the
	'everyone' row for user=None, which broke member removal (audit R2-3)."""
	for row in frappe.get_all(
		"DocShare", filters={"share_doctype": doctype, "share_name": name}, fields=["name", "user", "everyone"]
	):
		if not keep(row):
			# ignore_permissions: revoking access is a membership rule, not the current user's action.
			frappe.delete_doc("DocShare", row.name, ignore_permissions=True, force=True, flags=dict(REVOKE))
			if row.user:
				frappe.clear_cache(user=row.user)


def validate_share(doc, method=None):
	"""DocShare.validate: a scoped record may be shared only with members of its project (audit finding 1)."""
	from construction_core.accounts.guard import refuse_user_share

	refuse_user_share(doc)  # P3-14 (D-204): a User record only with its own user
	if (doc.share_doctype == "File" and doc.user and is_client(doc.user)
			and frappe.db.get_value("File", doc.share_name, "cc_version_of")):
		# P3-43 (D-305): by no one, a System Manager neither: an earlier version is the team's only
		frappe.throw(_("An earlier version of a file is never shared with clients"), frappe.PermissionError)
	if doc.share_doctype in APPROVAL_DOCTYPES:
		frappe.throw(_("Approval records are never shared"), frappe.PermissionError)  # P3-76: the read rule alone
	if doc.share_doctype not in SCOPED_DOCTYPES or _bypass(frappe.session.user):
		return
	record = frappe.get_doc(doc.share_doctype, doc.share_name)
	if (doc.share_doctype == "File" and not record.get("cc_project") and referenced_files(record)
			and (doc.everyone or not opens_as_its_file(record, "read", doc.user))):
		frappe.throw(_("This file can be shared only with people who may open the file it comes from"),
			frappe.PermissionError)  # P3-46 (D-308, D-311)
	project = project_of(record)
	if not project and doc.share_doctype in PASS_THROUGH_WHEN_EMPTY:
			return
	if doc.everyone:
		frappe.throw(_("Project records cannot be shared with everyone"), frappe.PermissionError)
	if not is_member(doc.user, project):
		frappe.throw(_("{0} is not a member of project {1}").format(doc.user, project), frappe.PermissionError)
	if is_client(doc.user):
		# A share must not give a client a doctype their role does not grant, or an internal file (audit R3), nor
		# a record of a project whose portal or section is switched off (P2-04 audit 3, D-117, D-098).
		if (doc.share_doctype not in CLIENT_READABLE or not client_may_see(record)
				or not client_portal_open(project) or not client_section_open(doc.share_doctype, project)):
			frappe.throw(_("This record cannot be shared with a client"), frappe.PermissionError)


def revoke_client_shares(project: str, doctypes=None):
	"""Remove the shares that give the project's clients its records (all client-readable doctypes, or `doctypes`).
	Called when the portal or a section is switched off (WorkspaceConfig.on_update): a DocShare is ORed around the
	§2.1 predicate, so a share made earlier would outlive the switch (P2-04 audit 3)."""
	doctypes = sorted(CLIENT_READABLE) if doctypes is None else list(doctypes)
	clients = {u for u in frappe.get_all("Project Member", filters={"parenttype": "Construction Project",
		"parent": project}, pluck="user") if u and is_client(u)}
	if not clients or not doctypes:
		return
	# One query for the clients' shares, one per doctype to keep those of this project: the cost does not grow with
	# the project's records (re-audit), only with the clients' shares.
	shares = frappe.get_all("DocShare", filters={"user": ["in", sorted(clients)],
		"share_doctype": ["in", doctypes]}, fields=["name", "share_doctype", "share_name", "user"])
	by_doctype = {}
	for row in shares:
		by_doctype.setdefault(row.share_doctype, []).append(row)
	for doctype, rows in by_doctype.items():
		if doctype == "Construction Project":
			here = {project}
		else:
			here = set(frappe.get_all(doctype, filters={"name": ["in", [r.share_name for r in rows]],
				project_field(doctype): project}, pluck="name"))
		for row in rows:
			if row.share_name in here:
				# ignore_permissions: revoking access is a rule of the project's switches, not the user's action.
				frappe.delete_doc("DocShare", row.name, ignore_permissions=True, force=True, flags=dict(REVOKE))
				frappe.clear_cache(user=row.user)


# --- §2.3 Project members -> User Permission sync ---------------------------------------------------------


def add_creator_as_member(doc, method=None):
	"""Project.before_insert: the creator joins the members table, so a later removal revokes (D-091)."""
	user = frappe.session.user
	if user in ("Administrator", "Guest") or is_client(user):
		return
	if not any(row.user == user for row in doc.get("users") or []):
		doc.append("users", {"user": user, "welcome_email_sent": 1})


def sync_user_permissions(doc, method=None):
	"""Project.after_insert / on_update: one User Permission per member, stale ones removed. Idempotent."""
	desired = {row.user for row in doc.get("users") or [] if row.user}
	existing = frappe.get_all(
		"User Permission", filters={"allow": "Construction Project", "for_value": doc.name}, fields=["name", "user"]
	)
	have = {row.user for row in existing}
	for user in desired - have:
		# ignore_permissions: membership is managed by this hook, not by the editing user's rights.
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Construction Project", "for_value": doc.name}
		).insert(ignore_permissions=True)
	for row in existing:
		if row.user not in desired:
			frappe.delete_doc("User Permission", row.name, ignore_permissions=True, force=True)
			revoke_member_shares(doc.name, row.user)
	for user in desired ^ have:
		frappe.clear_cache(user=user)


def cleanup_user_permissions(doc, method=None):
	"""Project.on_trash: remove the rows that would block deletion (DR-7). Must never raise.
	Its Workspace Config and its empty folders go too; a real file still blocks the delete on purpose, so a
	project with documents is archived instead (ARCHITECTURE §6.1)."""
	try:
		if frappe.db.exists("Workspace Config", doc.name):
			frappe.delete_doc("Workspace Config", doc.name, ignore_permissions=True, force=True)
		for _ in range(20):
			empty = [
				f for f in frappe.get_all("File", filters={"cc_project": doc.name, "is_folder": 1}, pluck="name")
				if not frappe.db.exists("File", {"folder": f})
			]
			if not empty:
				break
			for f in empty:
				frappe.delete_doc("File", f, ignore_permissions=True, force=True)
	except Exception:
		frappe.log_error(title=f"construction_core: workspace cleanup failed for {doc.name}")
	try:
		for row in frappe.get_all(
			"User Permission", filters={"allow": "Construction Project", "for_value": doc.name}, fields=["name", "user"]
		):
			frappe.delete_doc("User Permission", row.name, ignore_permissions=True, force=True)
			frappe.clear_cache(user=row.user)
	except Exception:
		frappe.log_error(title=f"construction_core: User Permission cleanup failed for {doc.name}")

