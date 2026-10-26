"""The deploy step for route rules (DR-2, D-050, D-054; ARCHITECTURE §3.2).

A route rule change is a deploy event. Frappe keeps its 404 answers per URL in `website_404`, with no expiry, and
reads them before any route rule; `frappe.website.utils.clear_cache()` alone does not reset the rest, and a worker
restart does not help (S10 F1). `deploy/init-site.sh` and `dev/up.sh` run this after every migrate:

    bench --site <site> execute construction_shell.deploy.clear_route_caches
"""

import frappe
from frappe.website.utils import clear_website_cache


def clear_route_caches() -> dict:
	frappe.clear_cache()
	clear_website_cache()
	return {"website_404": len(frappe.cache.hgetall("website_404") or {})}
