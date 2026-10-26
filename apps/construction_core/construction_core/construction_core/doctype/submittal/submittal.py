# Copyright (c) 2026, Construction Workspace and contributors
"""Submittal (ARCHITECTURE §9.2) with a revision child.

Draft -> Submitted -> Under Review -> Approved | Approved as Noted | Revise and Resubmit | Rejected.
"Revise and Resubmit" goes back to Submitted with a new revision row. A review decision needs the
``approve_submittal`` Permission Type (§2.4, D-028), and only that transition writes a ``review_outcome``.
A decided submittal (Approved, Approved as Noted, Rejected) is final and cannot be deleted; only a Draft can.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from construction_core.core.events import emit
from construction_core.permissions import _bypass

OUTCOMES = {"Approved", "Approved as Noted", "Revise and Resubmit", "Rejected"}
FINAL = {"Approved", "Approved as Noted", "Rejected"}
REVISION_FIELDS = ("revision_no", "submitted_on", "file", "review_outcome", "reviewer_comments")
TRANSITIONS = {
	"Draft": {"Submitted"},
	"Submitted": {"Under Review"},
	"Under Review": OUTCOMES,
	"Revise and Resubmit": {"Submitted"},
	"Approved": set(),
	"Approved as Noted": set(),
	"Rejected": set(),
}


class Submittal(Document):
	def before_insert(self):
		if self.status != "Draft":
			frappe.throw(_("A new submittal starts as Draft"))

	def validate(self):
		before = self.get_doc_before_save()
		if not before:
			for r in self.revisions:
				r.review_outcome = None
			return
		if before.status in FINAL and not _bypass(frappe.session.user):
			frappe.throw(_("A decided submittal is final: raise a new submittal instead"), title=_("Submittal decided"))
		decided = None
		if before.status != self.status:
			if self.status not in TRANSITIONS.get(before.status, set()):
				frappe.throw(_("A submittal cannot move from {0} to {1}").format(_(before.status), _(self.status)),
					title=_("Invalid state"))
			if self.status == "Submitted":
				self._open_revision()
			if self.status in OUTCOMES:
				frappe.has_permission("Submittal", "approve_submittal", doc=self, throw=True)
				if self.revisions:
					decided = self.revisions[-1]
					decided.review_outcome = self.status
		self._check_outcomes(before, decided)

	def _check_outcomes(self, before, decided):
		"""Review outcomes are written only by a review transition; revisions are never removed."""
		saved = {r.name: r for r in before.revisions}
		if set(saved) - {r.name for r in self.revisions}:
			frappe.throw(_("Submittal revisions cannot be removed"))
		for r in self.revisions:
			old = saved.get(r.name)
			expected = self.status if r is decided else (old.review_outcome or None if old else None)
			if (r.review_outcome or None) != expected:
				frappe.throw(_("Revision {0}: the review outcome is set by the review decision only").format(
					r.revision_no or r.idx), frappe.PermissionError)
			if old and old.review_outcome and any((r.get(f) or None) != (old.get(f) or None) for f in REVISION_FIELDS):
				frappe.throw(_("Revision {0} has been reviewed and cannot change").format(old.revision_no or old.idx),
					frappe.PermissionError)

	def _open_revision(self):
		self.current_revision = (self.current_revision or 0) + 1
		last = self.revisions[-1] if self.revisions else None
		if last and not last.review_outcome:
			# the open revision (added with its file) is the one being submitted; its number is the server's
			last.revision_no, last.submitted_on = self.current_revision, last.submitted_on or today()
			return
		self.append("revisions", {"revision_no": self.current_revision, "submitted_on": today()})

	def on_trash(self):
		if self.status != "Draft" and not _bypass(frappe.session.user):
			frappe.throw(_("Only a Draft submittal can be deleted"), frappe.PermissionError)

	def on_update(self):
		from construction_core.approvals import subjects  # here: approvals loads the ledger

		subjects.check(self)  # P3-77: the client's approval, on the saved terms (§3.10, §3.11)
		if self.has_value_changed("status"):
			emit("submittal.status_changed", self)
