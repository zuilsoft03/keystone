"""The /portal namespace (DR-3, ARCHITECTURE §3.2, P1-13).

- Guests are sent to the login page; staff (System Users) are sent to the workspace (P2-04: the ERPNext-era
  ``/app/project`` no longer exists since D-104).
- A project whose client portal is off is not readable by its clients at all (``permissions.client_portal_open``),
  so it ends in the same 404.
- ``/portal`` lists the client's projects; ``/portal/<project>`` shows one project;
  ``/portal/<project>/whiteboard/<board>`` shows a client-visible board, read-only (P1-15).
- Anything else, including a project the user may not read or that does not exist, gets the same 404 page whatever
  the requester, so the answer is safe to cache and reveals nothing (D-054).
- P2-06 (D-121): once every check above has passed, an installed presenter (hook ``cc_portal_renderer``) may present
  the page as a single-page app, which reads ``portal_api``; site config ``cc_portal_spa = 0`` keeps this
  server-rendered page. The 404 is always this page's own.
- P3-64 (R-32): this server-rendered page no longer posts. Its Discussion is a link to the portal app's Discussion tab
  (/portal/<project>?tab=discuss, keeping an old link's ?thread=) while the app serves the portal, and otherwise the
  Client room's latest messages, read-only (audit F3: a link would lead back here).
"""

from urllib.parse import quote, urlencode

import frappe

from construction_core import portal
from construction_core.permissions import client_sections_off, is_client

no_cache = 1


def get_context(context):
	request = getattr(frappe.local, "request", None)
	path = request.path if request else "/portal"
	user = frappe.session.user
	if user == "Guest":
		_redirect("/portal/login?redirect-to=" + quote(path, safe="/"))  # the clients' sign-in (D-265)
	if not is_client(user):
		_redirect("/workspace")
	context.no_cache = 1
	context.show_sidebar = False
	parts = [p for p in path.strip("/").split("/") if p]
	if parts[:1] != ["portal"]:
		return _not_found(context)
	parts = parts[1:]
	if not parts:
		context.view = "home"
		context.title = "Your projects"
		if _present(context):
			return context
		context.projects = portal.my_projects()
		return context
	if len(parts) == 1 and portal.can_read_project(parts[0]):
		context.view = "project"
		context.title = frappe.db.get_value("Construction Project", parts[0], "project_name") or parts[0]
		if _present(context):
			return context
		context.update(portal.project_view(parts[0], room_only=True))
		context.room = next((t for t in context.threads if t.room_key and t.audience == "Client"), None)
		context.title = context.project.project_name or context.project.name
		context.csrf_token = frappe.sessions.get_csrf_token()
		context.sections_off = client_sections_off(parts[0])  # D-098: the team's per-project section switches
		context.user = frappe.session.user
		# P3-64 (audit F3): a link to the portal app's Discussion only while the app serves the portal (else it would
		# lead back here); otherwise the Client room's latest messages, read-only.
		context.discussion_link = discussion_link(parts[0], request) if _app_serves() else ""
		return context
	if len(parts) == 3 and parts[1] == "whiteboard" and portal.can_read_project(parts[0]):
		view = portal.board_view(parts[0], parts[2])
		if view:
			context.view = "board"
			context.title = view["board"].title
			if _present(context):
				return context
			context.update(view)
			context.title = view["board"].title
			return context
	return _not_found(context)


def discussion_link(project: str, request) -> str:
	"""P3-64: the retired page's conversation is the portal app's Discussion tab, keeping an old link's ?thread=."""
	args = {"tab": "discuss"}
	thread = request.args.get("thread") if request is not None else None
	if isinstance(thread, str) and thread:
		args["thread"] = thread
	return f"/portal/{quote(project, safe='')}?" + urlencode(args)


def _app_serves() -> bool:
	return bool(frappe.get_hooks("cc_portal_renderer")) and bool(frappe.utils.cint(frappe.conf.get("cc_portal_spa", 1)))


def _present(context) -> bool:
	"""Hand the page to the installed presenter (P2-06). Called only after this page's checks have passed; the
	presenter receives the checked view and returns the app's script, styles and boot data, or None to decline."""
	hooks = frappe.get_hooks("cc_portal_renderer")
	if not hooks or not frappe.utils.cint(frappe.conf.get("cc_portal_spa", 1)):
		return False
	spa = frappe.get_attr(hooks[-1])(context)
	# Only a well-formed answer replaces this page; anything else keeps the server-rendered page (P2-06 audit 2).
	if not (isinstance(spa, dict) and isinstance(spa.get("script"), str) and isinstance(spa.get("styles"), list)
			and isinstance(spa.get("boot"), dict)):
		return False
	context.spa = spa
	context.portal_base = "construction_core/templates/cc_spa.html"
	context.csrf_token = frappe.sessions.get_csrf_token()
	return True


def _not_found(context):
	context.view = "not_found"
	context.title = "Not found"
	context.http_status_code = 404
	return context


def _redirect(location):
	frappe.local.flags.redirect_location = location
	raise frappe.Redirect
