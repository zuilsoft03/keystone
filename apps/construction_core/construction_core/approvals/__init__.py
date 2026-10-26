"""Client approvals (design docs/design/phase-3.5-approvals.md, R-33; D-423, D-428).

``log`` is the ledger's one writer, ``canonical`` its text and hashes, ``frozen`` the copies a client is shown and
``read`` the request's own read rule. The endpoint of P3-76 is ``file``; ``api`` holds P3-77's staff endpoints (the
set-up, ``request`` and ``make_variation``), ``subjects`` the four kinds a client approves and ``preflight`` its one
check; decide() and the others come with P3-78.
"""

import json
from datetime import timedelta
from urllib.parse import quote

import frappe
from frappe import _
from werkzeug.wrappers import Response

# Not the CSP of a page: a frozen PDF or picture opened on its own runs nothing, submits nothing, is framed by us only.
SANDBOX = "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox"
OPENED_WINDOW = timedelta(minutes=10)  # P3-77 (bypass-6): one opened event per person and copy in this window


@frappe.whitelist(methods=["GET"])
def file(request: str, key: str):
	"""One frozen copy of a request (§4.3), after the request's read rule: staff who read the project's requests, or a
	client through the rule (approvals.read). The stored type and name, nosniff, same-origin only, private no-cache;
	inline only for PNG, JPEG, WebP and PDF, under a sandbox policy; every other type downloads. Opening it writes an
	``opened`` event (who, which copy, when), at most one per person and copy in OPENED_WINDOW, so reloading a page
	does not grow the chain (bypass-6). Anything else is one "not found"."""
	from construction_core.approvals import frozen, log, read  # here: permissions imports approvals.read as it loads

	def serve():
		doc = read.readable(request)
		entry = frozen.entry_of(doc, key) if doc else None
		content = frozen.read(entry["shown_sha256"]) if entry else None
		if content is None:
			raise frappe.DoesNotExistError(_("Not found"))
		log.lock(doc.project, doc.name)  # and a locking read below: two loads at once see each other's event
		lately = frappe.db.sql("""select canonical from `tabApproval Event` where request = %s and kind = 'opened'
			and actor = %s and at_utc >= %s for update""", (doc.name, frappe.session.user,
			log._now().replace(tzinfo=None) - OPENED_WINDOW), pluck=True)
		if not any(json.loads(text)["body"].get("file") == key for text in lately):
			log.append_event(doc.project, "opened", request=doc.name, body={"file": key, "sha256": entry["shown_sha256"]})
		return entry, content

	entry, content = log.retry_once(serve)
	frappe.flags.commit = True  # a GET is rolled back at its end otherwise (frappe.app.sync_database)
	shown = "inline" if entry["type"] in frozen.INLINE else "attachment"
	return Response(content, status=200, content_type=entry["type"], headers={
		"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff",
		"Cross-Origin-Resource-Policy": "same-origin", "Content-Security-Policy": SANDBOX,
		"Content-Disposition": f"{shown}; filename*=UTF-8''{quote(entry.get('name') or 'file')}"})
