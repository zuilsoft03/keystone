"""An override holds by the function, not by the name (P3-76 round 5, D1). execute_cmd (/api/method and a form's
``cmd``) and v2's handle_rpc_call look ``override_whitelisted_methods`` up by the exact name sent, then call what that
name resolves to if it is whitelisted. Another importable name for a replaced function reaches Frappe's original and
skips the app's override: the package form of a function in an ``__init__.py`` (``frappe.email.__init__.relink`` runs
the module again, and its whitelist decorator registers the new function, at the same code location) and a module that
re-exports one (``frappe.api.v2.upload_file``). v2's own /api/v2/method/upload_file route calls Frappe's upload_file
with no override at all, and the mapper's and the tree view's calls dispatch a second name the same way (``method``,
``tree_method``).

``refuse_replaced_alias`` is a before_request hook: app.init_request runs it before application() dispatches a form's
cmd, /api/method, /api/v1 and /api/v2. It resolves each name the request dispatches as its dispatcher will (the
override first, so the name an override is registered under resolves to the override) and refuses a replaced function
by its code location. It imports only what that dispatcher imports next.
"""

import importlib
import inspect
import sys
from types import CodeType

import frappe
from frappe import _
from frappe.api import API_URL_MAP, v1, v2
from werkzeug.exceptions import HTTPException

# whitelisted calls that dispatch a second name the caller sends, applying the overrides by that exact name
NESTED = {"frappe.model.mapper.make_mapped_doc": "method", "frappe.model.mapper.map_docs": "method",
	"frappe.desk.treeview.get_all_nodes": "tree_method"}
_REPLACED = {}  # a replaced function's path -> its code location (None: it is its own override), once it is imported


def refuse_replaced_alias():
	called = {_location(fn) for fn in _dispatched() if fn}
	if called and called & _replaced():  # resolved first: _replaced reads only imported modules
		frappe.throw(_("This method is not available by that name"), frappe.PermissionError)


def _dispatched() -> list:
	"""The functions the request calls by a name it sends, in application()'s order: a form's cmd on any path, then
	/api/ routes (v1 and v2 RPC by name, any other endpoint as itself)."""
	form, request = frappe.form_dict, frappe.local.request
	if form.cmd:
		fn = _resolve(form.cmd)
	elif request.path.startswith("/api/"):
		try:
			endpoint, args = API_URL_MAP.bind_to_environ(request.environ).match()
		except HTTPException:
			return []  # the API answers it itself
		if endpoint is v1.handle_rpc_call:
			fn = _resolve(args["method"].split("/")[0])
		elif endpoint is v2.handle_rpc_call:
			fn = _resolve(_v2_name(args))
		else:
			fn = endpoint
	else:
		return []
	nested = NESTED.get(_path(fn))
	return [fn, _resolve(form.get(nested))] if nested else [fn]


def _v2_name(args):
	if not args.get("doctype"):
		return args["method"]
	from frappe.modules.utils import load_doctype_module
	try:
		return f"{load_doctype_module(args['doctype']).__name__}.{args['method']}"
	except Exception:
		return None  # handle_rpc_call fails on it too


def _resolve(name):
	"""The function a dispatcher calls for a name: its last override's, else its own (with no dot, a frappe.handler
	global, as execute_cmd has it); None where the dispatcher fails on the name itself."""
	if not name or not isinstance(name, str):
		return None
	module, _dot, attr = frappe.override_whitelisted_method(name).rpartition(".")
	if module and module.partition(".")[0] not in frappe.get_installed_apps():
		return None  # get_attr refuses it before any import
	try:
		return getattr(importlib.import_module(module or "frappe.handler"), attr, None)
	except Exception:
		return None


def _replaced() -> set:
	"""The code locations of the functions override_whitelisted_methods replaces, each read once its module is imported:
	a resolved alias's module (and an ``__init__`` form's package) is imported by then. A name whose function is its own
	override (Frappe's legacy File names) replaces nothing."""
	found = set()
	for name, paths in frappe.get_hooks("override_whitelisted_methods").items():
		for path in (name, *paths[:-1]):
			if path not in _REPLACED and (fn := _loaded(path)):
				_REPLACED[path] = _location(fn) if _location(fn) != _location(_loaded(paths[-1])) else None
			found.add(_REPLACED.get(path))
	return found - {None}


def _loaded(path):
	module, _dot, attr = path.rpartition(".")
	return getattr(sys.modules.get(module or "frappe.handler"), attr, None)


def _location(fn):
	code = getattr(inspect.unwrap(fn), "__code__", None)
	return (code.co_filename, code.co_firstlineno) if isinstance(code, CodeType) else None


def _path(fn):
	fn = inspect.unwrap(fn)
	return f"{getattr(fn, '__module__', '')}.{getattr(fn, '__name__', '')}"
