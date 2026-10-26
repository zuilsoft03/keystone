"""Event registry (ARCHITECTURE §1, DR-4): async, idempotent, isolated.

Handlers are declared by any installed app in ``hooks.py``::

	cc_event_handlers = {"rfi.created": ["my_app.handlers.on_rfi_created"]}

A handler is called as ``handler(event=..., doctype=..., doc_name=...)`` on the short queue after the current
transaction commits. Core imports no adapter: an adapter that is not installed has no handlers in the hooks, so
nothing runs (§1.3).
"""

import frappe

HOOK = "cc_event_handlers"
IDEMPOTENCY_TTL = 24 * 60 * 60


def _key(path: str, event: str, doctype: str, name: str, version: str) -> str:
	# §1.2: per handler, per document version. Site-prefixed through frappe.cache.make_key.
	return frappe.cache.make_key(f"cc:evt:{path}:{event}:{doctype}:{name}:{version}")


def emit(event: str, doc=None, *, doctype: str | None = None, name: str | None = None, version: str | None = None):
	"""Enqueue every handler of ``event`` once per (handler, event, document, version). Returns the paths queued."""
	doctype = doctype or doc.doctype
	name = name or doc.name
	version = str(version or (doc.get("modified") if doc else "") or "")
	queued = []
	handlers = frappe.get_hooks(HOOK) or {}  # get_hooks returns [] when no app declares the hook
	for path in handlers.get(event, []):
		if not frappe.cache.set(_key(path, event, doctype, name, version), "1", nx=True, ex=IDEMPOTENCY_TTL):
			continue  # this exact (handler, event, document, version) was already queued
		sync = bool(frappe.flags.cc_events_sync)  # tests only: run in-process instead of on the worker
		frappe.enqueue(
			"construction_core.core.events.run_handler",
			queue="short",
			enqueue_after_commit=not sync,
			now=sync,
			path=path,
			event_name=event,  # `event` is a reserved frappe.enqueue argument
			doctype=doctype,
			doc_name=name,
		)
		queued.append(path)
	return queued


def run_handler(path: str, event_name: str, doctype: str, doc_name: str):
	"""Isolation (§1.3): a failing handler logs to Error Log and never raises into the worker or the caller."""
	try:
		frappe.get_attr(path)(event=event_name, doctype=doctype, doc_name=doc_name)
	except Exception:
		frappe.log_error(title=f"construction_core event handler failed: {path} on {event_name} {doctype} {doc_name}")
