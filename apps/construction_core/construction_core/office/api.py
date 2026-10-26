"""Office editing on the ONLYOFFICE Document Server (P1-17; D-073, D-081, D-082, D-099, D-101).

The browser loads the editor from ``/office/`` (nginx -> the Document Server). The Document Server talks to the site
over the internal network only:
- it downloads the file from ``fetch``, whose link is signed for that file and expires;
- it reports to ``callback``, which checks our per-file signature and the Document Server's own JWT, and fetches an
  edited file only from the Document Server's cache on the internal network (no request goes elsewhere).

The document key is stored on the File (``cc_office_key``). It holds for a whole editing session, so a Ctrl+S save
(status 6) keeps everyone in the same session, and it changes when the session closes (status 2 or 4). A callback
for any other key is stale or replayed and writes nothing.

A save keeps the working File's URL, so every link to it keeps working: the new content is written in place when
the File owns its path, and the previous content becomes a version File at a path of its own, attached like the
working File and never shown to clients. (Frappe shares one path between Files with identical content; a shared
path is never written, the working File moves to its own path instead.)

The file of a Project Document past WIP is under review or final: it opens read-only, and edits that arrive
anyway are kept as a separate draft, never written over it.

Editing is for the project team, with write on the file. Our own session count (``cc_office_max_editors``,
unlimited by default: 9.4 Community reports no limit, measured in P1-17) opens extra editors read-only (D-082).
"""

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

import frappe
import requests
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import cint, get_fullname, now_datetime

from construction_core.permissions import is_client, is_member
from construction_core.providers.storage import file_stem as _stem
from construction_core.providers.storage import own_path as _own_path
from construction_core.providers.storage import write_atomic as _write

DOC_TYPES = {
	"word": {"docx", "doc", "odt", "rtf", "txt", "docm", "dotx"},
	"cell": {"xlsx", "xls", "ods", "csv"},
	"slide": {"pptx", "ppt", "odp"},
	"pdf": {"pdf"},  # P3-48: PDFs in the Document Server's PDF editor (view mode in the Files popup)
}
EXTENSIONS = {e: t for t, exts in DOC_TYPES.items() for e in exts}
LINK_TTL = 600  # seconds the Document Server may use a download link (it downloads when the editor opens)
EDITOR_TTL = 12 * 3600  # P3-13 (D-203): an editor's signed configuration lasts one working day
JWT_HEADER = "AuthorizationJwt"  # the Document Server's JWT_HEADER; Frappe treats "Authorization" as its own login
JWT_LEEWAY = 30  # seconds of clock difference allowed on the Document Server's exp
SESSIONS = "cc:office:sessions"  # document key (or "pending:<user>") -> json {"users": [...], "at": epoch}
SESSION_TTL = 12 * 3600  # a session the Document Server never closed stops counting after this
PENDING_TTL = 120  # an editor counts from when it opens until the Document Server reports it
LAST_SAVE = "cc:office:last"  # document key -> json {"iat": ..., "url": ...} of the last save applied
DRAFTS = "cc:office:drafts"  # document key -> the draft File holding edits to a locked file
MAX_DOWNLOAD = 100 * 1024 * 1024


# --- signing ----------------------------------------------------------------------------------------------


def _secret() -> str:
	s = frappe.conf.get("cc_office_jwt_secret")
	if not s:
		frappe.throw(_("Office editing is not configured on this site"))
	return s


def _b64(raw: bytes) -> str:
	return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def jwt_encode(payload: dict) -> str:
	head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
	body = _b64(json.dumps(payload, separators=(",", ":")).encode())
	sig = hmac.new(_secret().encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
	return f"{head}.{body}.{_b64(sig)}"


def jwt_decode(token: str) -> dict:
	try:
		head, body, sig = token.split(".")
		expected = hmac.new(_secret().encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
		if not hmac.compare_digest(_b64(expected), sig):
			raise ValueError("signature")
		if json.loads(base64.urlsafe_b64decode(head + "==")).get("alg") != "HS256":
			raise ValueError("alg")
		claims = json.loads(base64.urlsafe_b64decode(body + "=="))
		if "exp" in claims and float(claims["exp"]) < time.time() - JWT_LEEWAY:
			raise ValueError("expired")
		return claims
	except (ValueError, TypeError, json.JSONDecodeError) as e:
		raise frappe.PermissionError(_("Invalid Document Server token")) from e


def _sig(*parts) -> str:
	return hmac.new(_secret().encode(), "|".join(map(str, parts)).encode(), hashlib.sha256).hexdigest()


# --- files, keys and sessions ---------------------------------------------------------------------------------


def _file(name: str):
	f = frappe.get_doc("File", name)
	ext = (f.file_name or "").rsplit(".", 1)[-1].lower()
	if f.is_folder or ext not in EXTENSIONS:
		frappe.throw(_("This file cannot be opened in the office editor"))
	if not f.cc_project or f.cc_trashed or f.cc_version_of:  # P3-43: an earlier version opens read-only, by its link
		frappe.throw(_("Only project files open in the office editor"))
	return f, ext


def _from_client(f) -> bool:
	"""A file in the clients' own folders: one a client sent (P3-07), or a checked copy chat put in 06_Client/Discussion
	files for a conversation (P3-65, D-390), whose bytes clients read. Both open view-only and are never saved over, so
	no Office save rewrites client-visible bytes without the checks."""
	if is_client(f.owner):
		return True
	from construction_core.workspace import client_folders

	return bool(f.get("cc_project") and f.get("folder") and f.folder in set(client_folders(f.cc_project).values()) - {None})


def _view_only(f) -> bool:
	"""A file Office opens view-only and never saves over: a client's (``_from_client``), or one a conversation made (an
	upload or a checked copy, Team room too: P3-67 audit), which stays as it was sent (discuss.media.chat_made)."""
	from construction_core.discuss import media

	return _from_client(f) or media.chat_made(f.name)


def _locked(f) -> bool:
	"""The file of a Project Document under review or final (past WIP) must not change under it."""
	return bool(frappe.db.exists("Project Document", {"document_file": f.name, "status": ["!=", "WIP"]}))


def document_key(f) -> str:
	"""The editing session's key: kept for the whole session, changed when it closes (``_rotate_key``).

	A new key is agreed in Redis first (SET NX), so editors opening at the same moment, or after a request whose
	write was lost, get the same key; the File stores it for the session."""
	key = frappe.db.get_value("File", f.name, "cc_office_key")
	if not key:
		slot = frappe.cache.make_key(f"cc:office:newkey:{f.name}")
		frappe.cache.set(slot, f"{f.name}-{frappe.generate_hash(length=16)}", nx=True, ex=SESSION_TTL)
		key = frappe.safe_decode(frappe.cache.get(slot))
		frappe.db.set_value("File", f.name, "cc_office_key", key, update_modified=False)
	return key


def _rotate_key(f) -> str:
	frappe.cache.delete(frappe.cache.make_key(f"cc:office:newkey:{f.name}"))
	key = f"{f.name}-{frappe.generate_hash(length=16)}"
	frappe.db.set_value("File", f.name, "cc_office_key", key, update_modified=False)
	return key


def _sessions() -> dict:
	"""Live entries only: a session counts for SESSION_TTL, an opened editor not yet reported for PENDING_TTL."""
	now, live = time.time(), {}
	for k, v in (frappe.cache.hgetall(SESSIONS) or {}).items():
		k = k.decode() if isinstance(k, bytes) else k
		try:
			entry = json.loads(v)
			users, at = entry["users"], float(entry["at"])
		except (ValueError, TypeError, KeyError):
			continue
		if now - at < (PENDING_TTL if k.startswith("pending:") else SESSION_TTL):
			live[k] = users
	return live


def _opening_key(file: str) -> str:
	return frappe.cache.make_key(f"cc:office:opening:{file}")


def opening(file: str) -> bool:
	"""Whether an editor opened this file for editing and the Document Server has not reported it yet."""
	return bool(frappe.cache.get(_opening_key(file)))


def active_editors() -> set:
	return {u for users in _sessions().values() for u in users}


def _track(key: str, users: list):
	frappe.cache.hset(SESSIONS, key, json.dumps({"users": users, "at": time.time()}))


def _internal_site() -> str:
	return frappe.conf.get("cc_office_internal_site") or frappe.utils.get_url()


# --- the browser asks for an editor -------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def editor_config(file: str, view: int = 0) -> dict:
	"""The signed configuration for DocsAPI.DocEditor, edit or view mode. A POST: it stores the session key (Frappe
	does not commit a GET, and a key the Document Server holds but we never stored makes every save look stale).
	`view` asks for view mode whatever the user may do: the Files tab's viewer popup (P3-48, D-315) takes no edit
	session."""
	user = frappe.session.user
	if is_client(user):
		frappe.throw(_("Office editing is for the project team"), frappe.PermissionError)
	f, ext = _file(file)
	f.check_permission("read")
	can_write = f.has_permission("write")
	locked = can_write and _locked(f)
	from_client = _view_only(f)  # P3-07 (D-179): a file a client sent opens view-only, never saved over (P3-65, P3-67: and chat's)
	# P3-48 (D-327): a PDF measured in Takeoff gets new content only through Upload new version, which asks what happens
	# to its takeoff (D-302); in Office it opens view-only
	measured = can_write and _measured(f, ext)
	mode = "edit" if can_write and not locked and not measured and not from_client and not cint(view) else "view"
	limit = cint(frappe.conf.get("cc_office_max_editors"))
	limited = False
	if mode == "edit" and limit:
		editors = active_editors()
		if user not in editors and len(editors) >= limit:
			mode, limited = "view", True  # D-082: beyond our edit-session budget, open read-only
		elif user not in editors:
			_track(f"pending:{user}", [user])  # counts now, before the Document Server reports it
	if mode == "edit":  # P3-43: no new version is uploaded under an editor that is still opening
		frappe.cache.set(_opening_key(f.name), "1", ex=PENDING_TTL)
	key = document_key(f)
	exp = int(time.time()) + LINK_TTL
	site = _internal_site()
	config = {
		"documentType": EXTENSIONS[ext],
		"document": {
			"fileType": ext, "key": key, "title": f.file_name,
			"url": f"{site}/api/method/construction_core.office.api.fetch?file={f.name}&exp={exp}&sig={_sig('fetch', f.name, exp)}",
			"permissions": {"edit": mode == "edit", "review": mode == "edit", "comment": True, "download": True, "print": True},
		},
		"editorConfig": {
			"mode": mode,
			"callbackUrl": f"{site}/api/method/construction_core.office.api.callback?file={f.name}&sig={_sig('callback', f.name)}",
			"user": {"id": user, "name": get_fullname(user)},
			"lang": "en",
			"customization": {"forcesave": True, "compactHeader": True,
				**({"macros": False, "plugins": False} if from_client else {})},
		},
	}
	config["token"] = jwt_encode({**config, "exp": int(time.time()) + EDITOR_TTL})  # D-203: the grant expires
	return {"config": config, "mode": mode, "limited": limited, "locked": locked, "measured": measured,
		"from_client": from_client, "server": "/office/"}


def _measured(f, ext: str) -> bool:
	from construction_core.files import versions

	return ext == "pdf" and bool(versions.drawings(f))


def _refused_save(f, ext: str, content: bytes) -> str:
	"""Why an Office save of a PDF is not applied ('' when it is): a PDF's revision is a PDF that passes what a staff
	upload passes (versions.checked_content: the size limit, no scripts), and never one of a PDF measured in Takeoff
	(P3-48, D-327)."""
	if ext != "pdf":
		return ""
	if not content.startswith(b"%PDF-"):
		return "not a PDF"
	if _measured(f, ext):
		return "measured in Takeoff: a new version is uploaded, so its takeoff is asked about"
	from construction_core.files import versions

	queued = len(frappe.local.message_log)
	try:
		versions.checked_content(f, content)
	except frappe.ValidationError as e:
		del frappe.local.message_log[queued:]
		return str(e) or "refused"
	return ""


# --- the Document Server downloads and reports ------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["GET"])
def fetch(file: str, exp: str, sig: str):
	"""DR-5: a guest method that checks its own signature. Serves one file, for a limited time."""
	if not hmac.compare_digest(_sig("fetch", file, exp), sig or "") or cint(exp) < time.time():
		raise frappe.PermissionError(_("Invalid or expired link"))
	f, _ext = _file(file)
	frappe.response["filename"] = f.file_name
	frappe.response["filecontent"] = f.get_content()
	frappe.response["type"] = "download"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def callback(**_body):
	"""ONLYOFFICE's save callback. Must answer {"error": 0} or the Document Server retries.

	With a JSON body Frappe builds the arguments from the body only, so ``file`` and ``sig`` are read from the query
	string we signed, never from the body (whose keys arrive in ``_body`` and are ignored)."""
	file, sig = frappe.request.args.get("file"), frappe.request.args.get("sig")
	if not file or not hmac.compare_digest(_sig("callback", file), sig or ""):
		raise frappe.PermissionError(_("Invalid callback"))
	body = frappe.request.get_json(silent=True) or {}
	token = body.get("token") or (frappe.get_request_header(JWT_HEADER) or "").removeprefix("Bearer ").strip()
	if not token:
		raise frappe.PermissionError(_("Missing Document Server token"))
	claims = jwt_decode(token)
	data = claims.get("payload", claims)  # a header token wraps the body in "payload"
	f, ext = _file(file)
	key, status = data.get("key"), cint(data.get("status"))
	if not key or not str(key).startswith(f"{f.name}-"):
		raise frappe.PermissionError(_("The callback is for another document"))
	if key != document_key(f):
		return _ok()  # a closed session's report, or a replay: nothing to do
	users = [u for u in data.get("users") or [] if isinstance(u, str)]
	if status in (1, 2, 4):
		frappe.cache.delete(_opening_key(f.name))  # reported: the session itself counts now, or it is over
	if status == 1:
		_track(key, users)
		for u in users:
			frappe.cache.hdel(SESSIONS, f"pending:{u}")
	if status in (2, 6) and _view_only(f):  # P3-07: a client's file, or a chat file, is never saved over (it opens view-only)
		frappe.log_error(title="construction_core: office save refused", message=f"file={f.name} status={status}",
			defer_insert=True)
	elif status in (2, 6) and _fresh(key, claims.get("iat"), data.get("url")):
		content = _download_from_ds(data.get("url"))
		refused = _refused_save(f, ext, content)
		if refused:  # the save only: the session's own bookkeeping below still runs
			frappe.log_error(title="construction_core: office save refused", message=f"file={f.name}: {refused}",
				defer_insert=True)
		else:
			_apply_save(f, key, content, users)
			frappe.cache.hset(LAST_SAVE, key, json.dumps({"iat": claims.get("iat"), "url": data.get("url")}))
	if status in (2, 3, 4):
		frappe.cache.hdel(SESSIONS, key)
	if status in (2, 4):
		_rotate_key(f)  # the session is over: the next editor starts a new one on the saved content
		frappe.cache.hdel(LAST_SAVE, key)
		frappe.cache.hdel(DRAFTS, key)
	return _ok()


def _apply_save(f, key: str, content: bytes, users: list):
	# Act as the editor when they are still an enabled member (File hooks check membership); the callback itself is
	# authenticated twice (our per-file signature and the Document Server's JWT), so Administrator otherwise.
	members = [u for u in users if is_member(u, f.cc_project)]
	editor = next((u for u in members if cint(frappe.db.get_value("User", u, "enabled"))), None)
	turned_off = bool(members) and not editor  # P3-13 (D-203): every member editing has been turned off
	frappe.set_user(editor or "Administrator")
	if turned_off:
		save_draft(f, key, content, None, note=_("Edits from an editor whose access was turned off are kept as "
			"{0}; the file itself is unchanged"))
		frappe.log_error(title="construction_core: office save by a turned-off editor kept as a draft",
			message=f"file={f.name}", defer_insert=True)
	elif _locked(f):
		save_draft(f, key, content, editor or (users[0] if users else None))
	else:
		save_edited(f, content, editor or (users[0] if users else None))


def _ok():
	frappe.local.response.update({"error": 0})
	return {"error": 0}


def _fresh(key: str, iat, url) -> bool:
	"""Within a session, a save older than (or the same as) the last one applied is a replay."""
	last = frappe.cache.hget(LAST_SAVE, key)
	if not last:
		return True
	last = json.loads(last)
	if url and url == last.get("url"):
		return False
	try:
		return iat is None or last.get("iat") is None or float(iat) >= float(last["iat"])
	except (TypeError, ValueError):
		return False


def _download_from_ds(url: str | None) -> bytes:
	"""Fetch an edited file from the Document Server's cache, over the internal network only (no SSRF)."""
	path = urlparse(url or "").path
	marker = path.find("/cache/files/")
	if marker < 0 or ".." in path:
		frappe.throw(_("Unexpected file address from the Document Server"))
	internal = (frappe.conf.get("cc_office_internal_ds") or "http://documentserver").rstrip("/")
	query = urlparse(url).query
	r = requests.get(f"{internal}{path[marker:]}" + (f"?{query}" if query else ""), timeout=60, stream=True,
		allow_redirects=False)
	r.raise_for_status()
	if r.status_code != 200:  # a redirect or an empty reply is not the document
		frappe.throw(_("The Document Server did not return the edited file (HTTP {0})").format(r.status_code))
	content = r.raw.read(MAX_DOWNLOAD + 1, decode_content=True)
	if not content:
		frappe.throw(_("The Document Server returned an empty file"))
	if len(content) > MAX_DOWNLOAD:
		frappe.throw(_("The edited file is too large"))
	return content


# --- saving --------------------------------------------------------------------------------------------------


def _new_file(f, file_name: str, content: bytes, stem: str, ext: str):
	"""A File at a path of its own, attached like ``f`` so the team reads it, never shown to clients."""
	attached = ({"attached_to_doctype": f.attached_to_doctype, "attached_to_name": f.attached_to_name}
		if f.attached_to_doctype and f.attached_to_name else {"attached_to_doctype": "Construction Project", "attached_to_name": f.cc_project})
	doc = frappe.get_doc({"doctype": "File", "file_name": file_name, "file_url": _own_path(stem, ext, content),
		"is_private": 1, "folder": f.folder, "cc_project": f.cc_project, "cc_client_visible": 0,
		"content_hash": get_content_hash(content), "file_size": len(content), **attached})
	doc.flags.copy_from_existing_file = True  # our own new path: Frappe must not point it at an identical file
	# ignore_permissions: the Document Server's signed callback is the authority for an edit the user made.
	return doc.insert(ignore_permissions=True)


def _split(f):
	base, dot, ext = f.file_name.rpartition(".")
	return (base, f"{dot}{ext}") if dot else (f.file_name, "")


def save_edited(f, content: bytes, user: str | None) -> str:
	"""Write the new content into the working File (its URL stays); keep the previous content as a version File.
	P3-43 (D-301): each save is the file's next revision (files.versions.revise); the callback has checked it."""
	from construction_core.files.versions import revise

	out = revise(f.name, content, note=_("Saved in Office"), check=False, in_place=True, by=user or None,
		comment=_("Saved Rev {rev} from the online editor by {who}"),
		who=get_fullname(user) if user else _("the Document Server"))
	return out["version"]


def save_draft(f, key: str, content: bytes, user: str | None, note: str | None = None) -> str:
	"""Edits to a locked file: one draft File per session, beside it, for the team to issue as a new revision."""
	draft = frappe.cache.hget(DRAFTS, key)
	draft = draft.decode() if isinstance(draft, bytes) else draft
	if draft and frappe.db.exists("File", draft):
		d = frappe.get_doc("File", draft)
		if frappe.db.count("File", {"file_url": d.file_url}) == 1:
			_write(d.get_full_path(), content)  # our own path (``_own_path``), still not shared
		else:
			d.db_set("file_url", _own_path(_stem(_split(d)[0]), _split(d)[1], content))
		d.db_set({"content_hash": get_content_hash(content), "file_size": len(content)})
		return d.name
	base, ext = _split(f)
	stamp = now_datetime().strftime("%Y%m%d-%H%M%S")
	d = _new_file(f, f"{base} (edited {stamp}){ext}", content, _stem(f"{base}-edited-{stamp}"), ext)
	frappe.cache.hset(DRAFTS, key, d.name)
	f.add_comment("Info", note.format(d.file_name) if note else _(
		"{0} edited this file after its document left WIP; the edits are kept as {1}").format(
		get_fullname(user) if user else _("the Document Server"), d.file_name))
	return d.name
