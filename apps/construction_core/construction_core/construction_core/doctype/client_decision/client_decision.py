# Copyright (c) 2026, Construction Workspace and contributors
"""Client Decision (approvals design §3.3, §7; D-424): a client's choice among options, staff-only; the client sees it
only through its approval request.

Draft -> In internal review (P3-82: its request's internal steps first, staff-only) -> Waiting (a request is Open) ->
Decided (P3-78, from the answer; P3-82: after the after-client acknowledgements) or Needs a new request (after a
Return, a void or a replacement); Withdrawn and Changed (replaced by a later Decision through Replaces, its approval kept). Decided,
Withdrawn and Changed are final: only a System Manager still edits one (approvals.subjects records it). The status
follows the requests (approvals); a save may only withdraw. Staff edit in Draft, Waiting (the edit replaces the request)
and Needs a new request. Each option's key is the server's and never changes; once a request names the Decision, its
options are neither removed nor reordered.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from construction_core.permissions import _bypass

FINAL = {"Decided", "Withdrawn", "Changed"}
EDITABLE = {"Draft", "In internal review", "Waiting", "Needs a new request"}


class ClientDecision(Document):
	def validate(self):
		before = self.get_doc_before_save()
		was = before.status if before else "Draft"
		if was in FINAL and not _bypass(frappe.session.user):
			frappe.throw(_("A {0} decision is final: make a new one that replaces it").format(_(was)))
		if before and was == "Waiting":
			from construction_core.approvals import routes  # here: approvals loads the ledger

			why = routes.acknowledging(self.name)  # no bypass: a Waiting edit would supersede the approval
			if why:
				frappe.throw(why)
		if self.status != was and not (self.status == "Withdrawn" and was in EDITABLE):
			frappe.throw(_("A decision's status follows its approval requests: it can only be withdrawn"),
				frappe.PermissionError)
		if self.replaces and not before and (self.replaces == self.name or frappe.db.get_value(self.doctype,
				self.replaces, ["project", "status"]) != (self.project, "Decided")):
			frappe.throw(_("A decision replaces a decided decision of the same project"))
		keys = {o.name: o.option_key for o in before.options} if before else {}
		for o in self.options:
			o.option_key = keys.get(o.name) or frappe.generate_hash(length=10)
			o.cost_difference = flt(o.cost_difference, o.precision("cost_difference"))
		order = [o.name for o in sorted(self.options, key=lambda o: cint(o.idx))]  # as saved: rows keep a sent idx
		if keys and order[:len(keys)] != list(keys) and frappe.db.exists("Approval Request",
				{"subject_doctype": self.doctype, "subject_name": self.name}):
			frappe.throw(_("Once a decision was sent for approval, its options are neither removed nor reordered"))
		if self.recommended_option and self.recommended_option not in {o.option_key for o in self.options}:
			frappe.throw(_("The recommended option is one of the options"))

	def after_insert(self):
		if self.replaces:
			frappe.db.set_value(self.doctype, self.replaces, "status", "Changed")

	def on_update(self):
		from construction_core.approvals import subjects  # here: approvals loads the ledger

		subjects.check(self)

	def on_trash(self):
		if self.status != "Draft" and not _bypass(frappe.session.user):
			frappe.throw(_("Only a Draft decision can be deleted"), frappe.PermissionError)
