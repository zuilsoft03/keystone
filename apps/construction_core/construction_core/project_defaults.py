"""P3-55 (firm set-up W7): the defaults every new project takes, from the Defaults panel. System Managers only.

The folder tree is the Standard Folder Template (workspace.py builds each new project's folders from it); the rates are
Firm Settings' and fill a new project's empty rate fields (construction_project.py); the cost codes are the Cost Code
list. A project already made keeps its folders and its rates.
"""

import frappe
from frappe import _

from construction_core import workspace

RATES = ("default_vat", "default_retention", "default_withholding")
MAX_FOLDERS, MAX_CODES = 100, 500
KEEP = "06_Client"  # the client folders hang under it (workspace.ensure_client_folders, files/api.py)


def _mark(step: str, state: str) -> None:
	from construction_core.accounts.setup import mark  # S1's module; imported when used

	mark(step, state)


@frappe.whitelist()
def get() -> dict:
	frappe.only_for("System Manager")
	workspace.ensure_default_template()
	firm = frappe.get_single("Firm Settings")
	template = frappe.get_doc("Folder Template", workspace.DEFAULT_TEMPLATE)
	return {"folder_tree": [r.path for r in template.folders], **{f: firm.get(f) for f in RATES},
		"cost_codes": [{"code": c.code, "name": c.title} for c in
			frappe.get_all("Cost Code", fields=["code", "title"], order_by="code asc", limit=0)]}


@frappe.whitelist(methods=["POST"])
def save(folder_tree=None, default_vat=None, default_retention=None, default_withholding=None, cost_codes=None) -> dict:
	"""Only the parts given. W7 is done on a save."""
	frappe.only_for("System Manager")
	if folder_tree is not None:
		_save_tree(_json(folder_tree))
	rates = {"default_vat": default_vat, "default_retention": default_retention, "default_withholding": default_withholding}
	if any(v is not None for v in rates.values()):
		# locked like setup.mark's: a save from a stale copy would write back an old steps table
		firm = frappe.get_doc("Firm Settings", "Firm Settings", for_update=True)
		firm.update({k: v for k, v in rates.items() if v is not None})
		firm.save(ignore_permissions=True)  # its validate keeps each rate between 0 and 100; the caller is checked above
	if cost_codes is not None:
		_save_codes(_json(cost_codes))
	_mark("W7", "done")
	return get()


def _json(value):
	"""A list sent as JSON text (a form post) or as is; anything unreadable becomes None, which the checks refuse."""
	try:
		return frappe.parse_json(value)
	except ValueError:
		return None


def _save_tree(paths) -> None:
	if not isinstance(paths, list) or len(paths) > MAX_FOLDERS or not all(isinstance(p, str) for p in paths):
		frappe.throw(_("Give at most {0} folder paths.").format(MAX_FOLDERS))
	workspace.ensure_default_template()
	template = frappe.get_doc("Folder Template", workspace.DEFAULT_TEMPLATE)
	shown = {r.path: r.client_visible for r in template.folders}  # a kept folder keeps whether clients see it
	wanted = list(dict.fromkeys(p.strip().strip("/") for p in paths if p.strip()))
	if KEEP not in wanted:
		frappe.throw(_("The folder {0} holds the clients' files and stays.").format(KEEP))
	template.folders = []
	for path in wanted:
		template.append("folders", {"path": path[:140], "client_visible": shown.get(path, 0)})
	template.save(ignore_permissions=True)  # its validate keeps each path inside the project


def _save_codes(rows) -> None:
	if not isinstance(rows, list) or len(rows) > MAX_CODES or not all(isinstance(r, dict) for r in rows):
		frappe.throw(_("Give at most {0} cost codes.").format(MAX_CODES))
	wanted = {}
	for r in rows:
		code, title = (str(r.get("code") or "").strip()[:140], str(r.get("name") or "").strip()[:140])
		if not code or not title:
			frappe.throw(_("Each cost code needs a code and a name."))
		wanted[code] = title
	for code in frappe.get_all("Cost Code", pluck="name", limit=0):
		if code in wanted:
			continue
		try:
			frappe.delete_doc("Cost Code", code, ignore_permissions=True)
		except frappe.LinkExistsError:
			frappe.clear_messages()
			frappe.throw(_("The cost code {0} is used on a bill of quantities and stays.").format(code))
	for code, title in wanted.items():
		if frappe.db.exists("Cost Code", code):
			frappe.db.set_value("Cost Code", code, "title", title)
		else:
			frappe.get_doc({"doctype": "Cost Code", "code": code, "title": title}).insert(ignore_permissions=True)
