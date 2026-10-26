"""/login, /portal/login and /update-password drawn as the design's sign-in pages (P3-24, P3-26; D-250…D-252, D-264,
D-265).

Every path stays Frappe's in everything but the look: Frappe's own page context runs first (a signed-in visitor at a
sign-in page is redirected exactly as Frappe does), and the app signs in, resets and sets passwords only through
Frappe's own calls, under Frappe's own rules. The look is the group the address is for: LoginA for the team at /login,
LoginB for clients at /portal/login; any account signs in on either and lands in its own place. The password page
takes the look of the person whose reset key it is; an unknown and an expired key look the same (the team's), and
nothing about the person is put in the page beyond that look (whoever holds a live client key sees the client look). An installed presenter (hook ``cc_login_renderer``) draws the page as the
shell's sign-in app; without one, or if it breaks, Frappe's own template renders, so the site never loses its sign-in.
"""

from datetime import timedelta

import frappe
from frappe.utils import cint, now_datetime
from frappe.utils.data import sha256_hash

no_cache = 1

LOOKS = {"/login": "team", "/portal/login": "client"}


def get_context(context):
	request = getattr(frappe.local, "request", None)
	path = (request.path if request else "/login").rstrip("/") or "/login"
	view = "password" if path == "/update-password" else "login"
	if view == "login":
		from frappe.www.login import get_context as frappe_login

		try:
			frappe_login(context)  # raises frappe.Redirect for a signed-in visitor, as Frappe's own page does
		except frappe.Redirect:
			# Frappe sends a client to its role home page as a bare word ("portal"), which a browser resolves against
			# the page's own path: from /portal/login that is /portal/portal. Anchor it to the site's root.
			where = frappe.local.flags.redirect_location or "/"
			if "://" not in where and not where.startswith("/"):
				frappe.local.flags.redirect_location = "/" + where
			raise
		context.fallback = "frappe/www/login.html"
		look = LOOKS.get(path, "team")
	else:
		from frappe.www.update_password import get_context as frappe_password

		frappe_password(context)
		context.fallback = "frappe/www/update-password.html"
		look = password_look(frappe.form_dict.get("key"))
		context.referrer_policy = "no-referrer"  # the reset key is in this page's address
	context.cc_look = look
	context.title = "Sign in" if view == "login" else "Set your password"
	hooks = frappe.get_hooks("cc_login_renderer")
	try:
		spa = frappe.get_attr(hooks[-1])(context, view) if hooks else None
	except Exception:
		# A broken presenter must not take the sign-in with it: Frappe's own page renders instead.
		frappe.log_error(title="cc_login_renderer failed")
		spa = None
	if isinstance(spa, dict) and isinstance(spa.get("script"), str) and isinstance(spa.get("styles"), list) \
			and isinstance(spa.get("boot"), dict):
		context.spa = spa
		context.spa_base = "construction_core/templates/cc_spa.html"
		# A signed-in person changing their password posts with their session's token; a guest's calls need none.
		context.csrf_token = frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else ""
	return context


def password_look(key) -> str:
	"""The look of the password page: the signed-in person's group, else the reset key owner's while the key is live,
	else the team's. Read only: the GET never changes the key (Frappe checks and spends it on the POST)."""
	from construction_core.permissions import is_client

	if frappe.session.user != "Guest":
		return "client" if is_client(frappe.session.user) else "team"
	if not key or not isinstance(key, str) or len(key) > 128:
		return "team"
	row = frappe.db.get_value("User", {"reset_password_key": sha256_hash(key), "enabled": 1},
		["name", "last_reset_password_key_generated_on"], as_dict=True)
	if not row:
		return "team"
	expiry = cint(frappe.get_system_settings("reset_password_link_expiry_duration"))
	if expiry and (not row.last_reset_password_key_generated_on
			or now_datetime() > row.last_reset_password_key_generated_on + timedelta(seconds=expiry)):
		return "team"  # an expired key looks like an unknown one
	return "client" if is_client(row.name) else "team"
