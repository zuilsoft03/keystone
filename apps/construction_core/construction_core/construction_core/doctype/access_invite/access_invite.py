# Copyright (c) 2026, Construction Workspace and contributors
"""Access Invite (P3-16, R-13; D-187, D-209): one invitation link. System Manager only; the team acts on it through construction_core.onboarding.invites, which checks permission in its own body. Only the sha256 of the link's token is kept. Kind Owner (P3-54, D-346): the firm owner's invitation, made by Administrator
through construction_core.accounts.setup.invite_owner only."""

import frappe
from frappe import _
from frappe.model.document import Document


class AccessInvite(Document):
	def validate(self):
		# An Owner invitation grants the owner's roles at join: only invite_owner makes one, never a Desk or REST write.
		before = self.get_doc_before_save()
		if self.kind == "Owner" and (not before or before.kind != "Owner") and not self.flags.cc_owner_invite:
			frappe.throw(_("The owner's invitation is sent from the set-up wizard."), frappe.PermissionError)

	def before_insert(self):
		if self.kind == "Owner":
			self.invited_by = frappe.session.user  # join checks the inviter; never a caller's value
