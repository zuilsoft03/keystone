# Copyright (c) 2026, Construction Workspace and contributors
"""WBS Node: project -> phase -> trade -> sub-trade tree (ARCHITECTURE §6.5)."""

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class WBSNode(NestedSet):
	nsm_parent_field = "parent_wbs_node"

	def validate(self):
		if self.parent_wbs_node:
			parent_project = frappe.db.get_value("WBS Node", self.parent_wbs_node, "project")
			if parent_project != self.project:
				frappe.throw(_("A WBS node and its parent must belong to the same project"))
		dup = frappe.db.exists("WBS Node", {"project": self.project, "wbs_code": self.wbs_code, "name": ["!=", self.name]})
		if dup:
			frappe.throw(_("WBS code {0} already exists in project {1}").format(self.wbs_code, self.project))
