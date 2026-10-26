"""The /workspace entry page (ARCHITECTURE §3.2, P2-02; D-050, D-051, D-054, D-067, DR-3).

Every path under /workspace reaches this page through the two route rules in hooks.py (D-108). In this order:

1. A path the app does not know gets our own 404, the same for every requester (D-054). It depends only on the path,
   never on the user or on data, and it is not Frappe's not-found page, so nothing is written to the website 404 cache.
2. A Guest is sent to the login page.
3. A signed-in user who is not a System User (a client, a Website User) is refused in the page body (S10 F3, D-051):
   the entry gate turns away Guests only.
4. A System Manager opening the dashboard itself (`/workspace`, never a deep link) before set-up is finished, and who
   has not chosen "Finish later", is sent to `/workspace/setup` (P3-52, D-347, T8). Nobody else; Desk is never sent.
5. A System User gets the app. Which projects and records they see is decided by the server on every call; the app
   only presents. A project or record the user cannot open ends in the app's own "not found" view.
"""

import html
import json
import os
import re
from functools import lru_cache
from urllib.parse import quote

import frappe

from construction_core.accounts import setup
from construction_core.brand import public
from construction_core.onboarding.mail import PRODUCT_NAME, brand_name, credited
from construction_core.onboarding.mail import brand as company_name
from construction_shell.preferences import mode_of

PREFIX = "workspace"
SHELL_ASSETS = "/assets/construction_shell/shell/"
FAVICON = "/assets/construction_shell/favicon.svg"  # mark B, light tone (P3-44); the firm's logo replaces it (P3-45)
TOUCH_ICON = "/assets/construction_shell/icon-192.png"
TILE_FALLBACK = "\u2022"  # a bullet: the tile's letter when a firm's name does not start with a letter or a digit
ENTRY = "src/main.js"


@lru_cache(maxsize=1)
def sections() -> dict:
	with open(os.path.join(os.path.dirname(__file__), "sections.json"), encoding="utf-8") as f:
		return json.load(f)


def known_path(path: str) -> bool:
	"""Whether `path` is a shape the app knows: /workspace[/<project>[/<section>[/<item>[/<action>]]]]."""
	parts = [p for p in path.split("/") if p]
	if parts[:1] != [PREFIX]:
		return False
	spec = sections()
	segment = re.compile(spec["segment"])
	rest = parts[1:]
	if not rest:
		return True
	if len(rest) > 4 or not all(segment.fullmatch(p) for p in rest):  # fullmatch: `$` alone admits a trailing \n
		return False
	if len(rest) == 1:
		return True
	section = spec["sections"].get(rest[1])
	if not section:
		return False
	if len(rest) == 2:
		return True
	if not section["item"]:
		return False
	return len(rest) == 3 or rest[3] in section["actions"]


def brand_boot() -> dict:
	"""P3-44 (D-298, D-401…D-404): what every page of the shell shows as its name, from the one place the default lives:
	the product name (mail.PRODUCT_NAME; a firm never renames it, D-445), the company name (the Brand page's, else site
	config cc_company_name, D-210; "" until it is set), the name that leads (the company's, else the product's) and whether
	the small "Powered by" credit shows (once a company leads). The credit has no setting that removes it (D-404).
	P3-45 (D-300): ``brand`` adds the firm's logo, colours, heading font and default sign-in picture (brand.public(), ""
	for each one unset), with the four names above repeated, so a page reads its whole brand from one key."""
	names = {"product_name": PRODUCT_NAME, "company": company_name(), "brand_name": brand_name(), "credit": credited()}
	return {**names, "brand": {**public(), **names}}


def tab_title(page: str) -> str:
	"""The browser tab: "Page · Firm", or "Page · Keystone" until a firm leads (D-401, D-403). The page is a fixed word
	or the person's own project name."""
	page = (page or "").strip()
	return f"{page} · {brand_name()}" if page else brand_name()


def tile_letter(company: str) -> str:
	"""The letter on a firm's tile: the first character of its name when that is a letter or a digit, capitalised; else a
	fixed glyph, so a symbol, a control character or a lone surrogate can never break the icon's markup or its URL."""
	first = (company or "").strip()[:1]
	return first.upper()[:1] if first.isalnum() else TILE_FALLBACK


def favicon() -> str:
	"""The tab's icon: the firm's logo once uploaded (P3-45); else mark B until a firm leads; then a tile with the firm's
	initial, as in the pages (D-403)."""
	company = company_name()
	if not company:
		return FAVICON  # a logo alone never leads (D-403): the page shows Keystone, so does the tab
	logo = public()["logo_url"]
	if logo:
		return logo
	svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#0289f7"/>'
		'<text x="16" y="23.5" font-family="sans-serif" font-size="20" font-weight="700" text-anchor="middle" fill="#fff">'
		f"{html.escape(tile_letter(company))}</text></svg>")
	return "data:image/svg+xml," + quote(svg)


def is_staff(user: str) -> bool:
	return user != "Guest" and frappe.get_cached_value("User", user, "user_type") == "System User"


def get_context(context):
	request = getattr(frappe.local, "request", None)
	path = request.path if request else "/" + PREFIX
	context.no_cache = 1
	if not known_path(path):
		return _view(context, "not_found", "Not found", 404)
	user = frappe.session.user
	if user == "Guest":
		_redirect("/login?redirect-to=" + quote(path, safe="/"))  # every other character encoded, so nothing joins the query (P3-26)
	if not is_staff(user):
		return _view(context, "refused", "Not available", 403)
	if path.rstrip("/") == "/" + PREFIX and to_setup(user):
		_redirect("/" + PREFIX + "/setup", 302)  # never 301: a browser would keep it after set-up is finished
	assets = shell_assets()
	if not assets:
		return _view(context, "not_built", "Not available", 503)
	context.update(assets)
	context.boot = boot(user)  # the template serialises it with `tojson`, which escapes <, > and & for a <script>
	context.csrf_token = frappe.sessions.get_csrf_token()
	return _view(context, "app", "Workspace", 200)


def to_setup(user: str) -> bool:
	return "System Manager" in frappe.get_roles(user) and not setup.finished() and not setup.later(user)


def boot(user: str) -> dict:
	"""What the app needs before its first call. Nothing here is a permission: the server checks every call."""
	manager = "System Manager" in frappe.get_roles(user)
	return {
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"email": frappe.get_cached_value("User", user, "email") or user,
		"user_image": frappe.get_cached_value("User", user, "user_image") or "",
		"sitename": frappe.local.site,
		**brand_boot(),
		"desk": "/app",
		"mode": mode_of(user),  # Simple or Advanced (D-154): a view preference, not a permission
		"system_manager": manager,  # shows the People link; the server checks (D-235)
		**({"setup": {"finished": setup.finished(), "later": setup.later(user)}} if manager else {}),  # P3-52 (T9)
		"map_tiles": map_tiles(),  # P3-09 (D-157)
	}


OSM = {"url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "attribution": "© OpenStreetMap contributors"}


def map_tiles() -> dict | None:
	"""P3-09 (D-157): the map's background. OpenStreetMap's public tiles unless site config cc_map_tiles names another
	https source ({"url": ".../{z}/{x}/{y}.png", "attribution": "..."}) or is "off" (no map at all)."""
	conf = frappe.conf.get("cc_map_tiles")
	if conf in (None, ""):
		return OSM
	if conf == "off" or not isinstance(conf, dict):
		return None
	url, attribution = str(conf.get("url") or ""), str(conf.get("attribution") or "")[:200]
	if not url.startswith("https://") or not all(k in url for k in ("{z}", "{x}", "{y}")) or not attribution:
		return None  # a source we cannot credit or reach safely: no map rather than a broken one
	return {"url": url[:300], "attribution": attribution}


def shell_assets(entry: str = ENTRY) -> dict | None:
	"""A built entry's script and stylesheets, from Vite's manifest; None when the app is not built."""
	manifest = frappe.get_app_path("construction_shell", "public", "shell", ".vite", "manifest.json")
	try:
		with open(manifest, encoding="utf-8") as f:
			chunks = json.load(f)
		main = chunks[entry]
	except (OSError, ValueError, KeyError):
		return None
	# An entry's styles include those of the chunks it imports: with three entries Vite moves the shared stylesheet
	# into a common chunk (P3-17, D-215), as it may for any entry.
	styles, seen = [], set()

	def collect(name):
		if name in seen or name not in chunks:
			return
		seen.add(name)
		for imported in chunks[name].get("imports", []):
			collect(imported)
		for css in chunks[name].get("css", []):
			if SHELL_ASSETS + css not in styles:
				styles.append(SHELL_ASSETS + css)

	collect(entry)
	return {"script": SHELL_ASSETS + main["file"], "styles": styles, "favicon": favicon()}


def _view(context, view, title, status):
	context.view = view
	context.title = tab_title(title)
	context.favicon = favicon()
	context.touch_icon = "" if company_name() else TOUCH_ICON  # the app icon is Keystone's mark: only while Keystone leads
	context.http_status_code = status
	return context


def _redirect(location, status=301):
	frappe.local.flags.redirect_location = location
	raise frappe.Redirect(status)
