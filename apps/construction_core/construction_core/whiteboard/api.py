"""Whiteboard API (P1-15, D-099): load, save with conflict detection, version history, restore.

- Staff with write on the Whiteboard save; clients only read boards marked client visible (permission layer).
- A save names the version it started from. If someone saved in between, nothing is written and the caller gets
  the current scene back, so no one silently overwrites a colleague (Excalidraw's own merge happens client side).
- Every save is kept as a Whiteboard Version. A scene is sanitised: only http(s) and mailto links survive, and
  embedded web pages (iframes) are dropped, and images must be embedded base64 data, so a board never loads
  outside content into a client's browser.
- P3-75: after a save the editor sends its picture of the board (``snapshot``), the board's preview for cards and lists.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, get_fullname, now_datetime, time_diff_in_seconds

from construction_core.core.events import emit
from construction_core.permissions import client_section_open, is_client

MAX_SCENE_BYTES = 15 * 1024 * 1024
SAVED_EVENT = "cc_whiteboard_saved"
SAFE_LINK = ("http://", "https://", "mailto:")
DROPPED_TYPES = {"embeddable", "iframe"}
# Bidirectional and invisible formatting characters can disguise a link's text (P1-15 audit).
DISGUISE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
# Board images are embedded data only; any other address would make a viewer's browser fetch it (P1-15 audit).
IMAGE_DATA = re.compile(r"^data:(image/(?:png|jpeg|gif|webp|svg\+xml));base64,[A-Za-z0-9+/=]+$")
KEPT_APP_STATE = ("viewBackgroundColor", "gridSize")


def _board(name: str, ptype: str = "read"):
	doc = frappe.get_doc("Whiteboard", name)
	doc.check_permission(ptype)
	return doc


def _staff():
	if is_client(frappe.session.user):
		frappe.throw(_("Clients view boards; the project team edits them"), frappe.PermissionError)


def sanitise(scene) -> str:
	if isinstance(scene, str):
		try:
			scene = json.loads(scene)
		except (ValueError, RecursionError):
			frappe.throw(_("The board could not be read"))
	if not isinstance(scene, dict) or not isinstance(scene.get("elements", []), list):
		frappe.throw(_("The board could not be read"))
	elements = []
	for el in scene.get("elements") or []:
		if not isinstance(el, dict) or str(el.get("type") or "").lower() in DROPPED_TYPES:
			continue
		link = el.get("link")
		if link and (not str(link).strip().lower().startswith(SAFE_LINK) or DISGUISE.search(str(link))):
			el["link"] = None
		elements.append(el)
	app_state = scene.get("appState") if isinstance(scene.get("appState"), dict) else {}
	files = {}
	for key, f in (scene.get("files") if isinstance(scene.get("files"), dict) else {}).items():
		m = IMAGE_DATA.match(str(f.get("dataURL") or "")) if isinstance(f, dict) else None
		if m and f.get("mimeType") == m.group(1):
			files[key] = f
	out = json.dumps({"elements": elements, "appState": {k: app_state[k] for k in KEPT_APP_STATE if k in app_state},
		"files": files}, separators=(",", ":"))
	if len(out.encode()) > MAX_SCENE_BYTES:
		frappe.throw(_("The board is too large (over {0} MB): remove some images").format(MAX_SCENE_BYTES // 1024 // 1024))
	return out


def _last_save(by, on) -> dict:
	"""The board's last save for the team's title line (D-170): the saver's full name and the seconds since, site time."""
	if not by or not on:
		return {"saved_by_name": None, "saved_age": None}
	return {"saved_by_name": get_fullname(by), "saved_age": max(0, cint(time_diff_in_seconds(now_datetime(), on)))}


def board_data(b, user: str | None = None) -> dict:
	"""The board as ``user`` (None: the session user) gets it from load; the caller has checked that ``user`` reads it.
	The staff preview (P3-05) passes its client, so it shows exactly the client's own answer."""
	staff = not is_client(user or frappe.session.user)
	out = {"name": b.name, "title": b.title, "project": b.project, "version": cint(b.version),
		"client_visible": cint(b.client_visible), "scene": json.loads(b.scene or "{}"),
		"can_edit": staff and b.has_permission("write", user=user)}
	if staff:
		out.update(_last_save(b.last_saved_by, b.last_saved_on))  # the team's line; clients never get it
	return out


@frappe.whitelist()
def load(name: str) -> dict:
	return board_data(_board(name))


@frappe.whitelist(methods=["POST"])
def save(name: str, scene: str, base_version: int | str) -> dict:
	_staff()
	b = _board(name, "write")
	clean = sanitise(scene)
	try:
		current = cint(frappe.db.get_value("Whiteboard", name, "version", for_update=True))
	except frappe.QueryDeadlockError:
		current = -1  # someone saved at the same moment: report a conflict
	if current != cint(base_version):
		fresh = frappe.db.get_value("Whiteboard", name, ["version", "scene", "last_saved_by", "last_saved_on"], as_dict=True)
		return {"conflict": True, "version": cint(fresh.version), "scene": json.loads(fresh.scene or "{}"),
			**_last_save(fresh.last_saved_by, fresh.last_saved_on)}
	version = current + 1
	b.scene, b.version, b.scene_size = clean, version, len(clean.encode())
	b.last_saved_by, b.last_saved_on = frappe.session.user, now_datetime()
	b.flags.cc_scene_save = True
	b.save()
	# ignore_permissions: the snapshot is a consequence of a save the user was allowed to make.
	frappe.get_doc({"doctype": "Whiteboard Version", "whiteboard": name, "project": b.project, "version": version,
		"saved_by": frappe.session.user, "saved_on": b.last_saved_on, "scene_size": b.scene_size, "scene": clean,
	}).insert(ignore_permissions=True)
	emit("whiteboard.saved", b, version=f"{version}:{b.last_saved_on}")  # P3-69 (§3.9): a design event after the commit
	payload = {"name": name, "version": version, "by": frappe.session.user}
	frappe.publish_realtime(SAVED_EVENT, payload, doctype="Whiteboard", docname=name, after_commit=True)  # staff
	if b.client_visible and client_section_open("Whiteboard", b.project):
		from construction_core.discuss.api import client_members

		for user in client_members(b.project):
			frappe.publish_realtime(SAVED_EVENT, payload, user=user, after_commit=True)  # D-100: clients' own rooms
	return {"conflict": False, "version": version}


@frappe.whitelist(methods=["POST"])
def snapshot(name: str, version: int | str, image: str) -> dict:
	"""P3-75 (design §15.2): the editor's picture of the board after a save, for its preview. Staff who edit the board
	only, for its current version only; a picture that fails its checks is refused and the board is unchanged."""
	from construction_core.previews import boards

	_staff()
	_board(name, "write")
	return boards.take(name, cint(version), image)


@frappe.whitelist()
def versions(name: str) -> list:
	_staff()
	_board(name)
	return frappe.get_all("Whiteboard Version", filters={"whiteboard": name},
		fields=["name", "version", "saved_by", "saved_on", "scene_size"], order_by="version desc", limit=100)


@frappe.whitelist(methods=["POST"])
def restore(name: str, version: int | str) -> dict:
	"""Save an earlier version as the newest one (history is never rewritten)."""
	_staff()
	b = _board(name, "write")
	scene = frappe.db.get_value("Whiteboard Version", {"whiteboard": name, "version": cint(version)}, "scene")
	if scene is None:
		frappe.throw(_("Version {0} does not exist").format(version))
	return save(name, scene, b.version)


@frappe.whitelist(methods=["POST"])
def thread(name: str, audience: str = "Internal") -> str:
	"""The board's discussion thread, created on first use (P1-12 rules decide who may open which). Its title is the
	neutral "Board WB-…", never the board's own title, which a client would keep after an unshare (F11)."""
	from construction_core.discuss.provider import DiscussChat

	_board(name)
	return DiscussChat().ensure_thread("Whiteboard", name, audience)
