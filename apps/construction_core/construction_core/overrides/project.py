"""Construction Project extension (v16 ``extend_doctype_class``): creating a project is a role decision.

1. Creating a project is a role decision (D-091). A member's User Permission on ``Project`` also restricts the
   Project doctype itself, and v16 applies that to a brand-new record (``frappe/permissions.py
   has_user_permission``, step 1), so every existing member was refused "create". The check below uses role
   permissions for a project that does not exist yet; the creator then becomes a member, and every later read or
   write goes through the §2.1 predicate.
2. (P1-20, D-104) ERPNext's member DocShares (``control_access_for_project_users``) are gone with ERPNext: the role
   grants read and the §2.1 predicate scopes it.
"""

import frappe


class ProjectMembership:
	def check_permission(self, permtype="read", permlevel=None):
		if permtype == "create" and not frappe.db.exists("Construction Project", self.name):
			if frappe.has_permission("Construction Project", "create"):  # doctype level: role permissions only
				return
		return super().check_permission(permtype, permlevel)
