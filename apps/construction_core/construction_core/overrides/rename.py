"""A rename always runs its checks (P3-76, bypass-7). ``Document.rename`` is whitelisted with ``validate_rename`` and
``force``, so whoever reads a record could rename it with no write or allow_rename check and no before_rename hook
(v1's run_doc_method, the v1 and v2 document method routes), and whoever writes it could skip allow_rename. The
refusal then comes before rename_doc does any work (Link rewrites across tables, a DocType's committed table rename).
Extended on DocType, User and every project-scoped doctype; permissions.refuse_unchecked_rename is the backstop for
the others.

``rename_doc`` here overrides the whitelisted ``frappe.rename_doc``, which takes ``force`` straight from the caller
(round 3 fix round 4): force is kept only for a System Manager or setup.
"""

import frappe
from frappe import _

from construction_core.permissions import in_setup


class CheckedRename:
	def _rename(self, name, merge=False, force=False, validate_rename=True):
		if not in_setup():
			manager = "System Manager" in frappe.get_roles()
			if self.doctype == "User" and not manager:  # a User is the sign-in: renaming it re-addresses the account
				frappe.throw(_("Only an administrator can change a sign-in address."), frappe.PermissionError)
			force, validate_rename = force if manager else False, True
		return super()._rename(name, merge=merge, force=force, validate_rename=validate_rename)


@frappe.whitelist(methods=["POST", "PUT"])
def rename_doc(doctype, old, new, force=False, merge=False, *, ignore_if_exists=False, show_alert=True,
		rebuild_search=True):
	"""Override of the whitelisted ``frappe.rename_doc`` (round 3 fix round 4, bypass-7): it passes ``force`` straight to
	rename_doc, so staff with write could rename a record whose allow_rename is 0 (CheckedRename covers Document._rename,
	not this path). Keep force only for a System Manager or setup; validate stays on."""
	if force and not (in_setup() or "System Manager" in frappe.get_roles()):
		force = False
	return frappe.rename_doc(doctype, old, new, force=force, merge=merge, ignore_if_exists=ignore_if_exists,
		show_alert=show_alert, rebuild_search=rebuild_search)
