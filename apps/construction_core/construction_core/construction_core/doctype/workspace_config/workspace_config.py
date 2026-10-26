# Copyright (c) 2026, Construction Workspace and contributors
"""Workspace Config: one per project (P1-05). Its folder map is written by the system only (P1-11 exit audit)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from construction_core.permissions import CLIENT_SECTION, revoke_client_shares


class WorkspaceConfig(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if not self.flags.cc_system:
			self.folders = before.folders if before else None
		self._only_close_closes(before)

	def _only_close_closes(self, before):
		# P3-59: only Close project (projects_close.close) archives a project or dates its close; a manager's REST or
		# Desk save may not archive, reopen or backdate it (the 90-day client clock reads closed_on).
		if self.flags.cc_closing:
			return
		was = before or frappe._dict()
		if cint(self.archived) != cint(was.archived) or str(self.closed_on or "") != str(was.closed_on or ""):
			frappe.throw(_("Use Close project to close a project."), frappe.PermissionError)

	def on_update(self):
		"""Switching the portal, or a section, off for clients revokes their shares there (P2-04 audit 3, D-117)."""
		before = self.get_doc_before_save()
		if not before:
			return
		if before.client_portal_enabled and not self.client_portal_enabled:
			revoke_client_shares(self.project)
			return
		off_before = {s.section for s in before.sidebar_sections if not s.client_visible}
		newly_off = {s.section for s in self.sidebar_sections if not s.client_visible} - off_before
		doctypes = [dt for dt, sec in CLIENT_SECTION.items() if sec in newly_off]
		if doctypes:  # a section with no client records (e.g. takeoff) revokes nothing
			revoke_client_shares(self.project, doctypes)
