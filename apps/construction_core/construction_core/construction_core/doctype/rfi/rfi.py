# Copyright (c) 2026, Construction Workspace and contributors
"""RFI (ARCHITECTURE §9.1): Draft -> Issued -> Answered -> Closed; Answered may be re-opened to Issued.
A daily job emits ``rfi.overdue`` for every Issued RFI past its due date.

Accountability fields are set by the server only: ``raised_by`` at insert, ``answered_by``/``answered_on`` on the
Answered transition. The response is locked once answered, a Closed RFI is final, and only a Draft can be deleted.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, today

from construction_core.core.events import emit
from construction_core.permissions import _bypass

TRANSITIONS = {
	"Draft": {"Issued"},
	"Issued": {"Answered"},
	"Answered": {"Closed", "Issued"},
	"Closed": set(),
}
SERVER_FIELDS = ("raised_by", "answered_by", "answered_on")


class RFI(Document):
	def before_insert(self):
		self.raised_by = frappe.session.user
		self.answered_by = self.answered_on = None
		if self.status != "Draft":
			frappe.throw(_("A new RFI starts as Draft"))

	def validate(self):
		before = self.get_doc_before_save()
		if not before:
			return
		if before.status == "Closed" and not _bypass(frappe.session.user):
			frappe.throw(_("A closed RFI is final"), title=_("RFI closed"))
		for f in SERVER_FIELDS:
			self.set(f, before.get(f))
		if before.status == "Answered" and (self.response or "") != (before.response or ""):
			frappe.throw(_("The response is locked once answered: re-open the RFI first"))
		if before.status != self.status:
			if self.status not in TRANSITIONS.get(before.status, set()):
				frappe.throw(_("An RFI cannot move from {0} to {1}").format(_(before.status), _(self.status)),
					title=_("Invalid state"))
			if self.status == "Answered":
				if not (self.response or "").strip():
					frappe.throw(_("Write the response before marking the RFI answered"))
				self.answered_by = frappe.session.user
				self.answered_on = now_datetime()
			if self.status == "Issued" and not self.due_date:
				frappe.throw(_("Set a due date before issuing the RFI"))

	def on_trash(self):
		if self.status != "Draft" and not _bypass(frappe.session.user):
			frappe.throw(_("Only a Draft RFI can be deleted"), frappe.PermissionError)

	def after_insert(self):
		emit("rfi.created", self)

	def on_update(self):
		if self.has_value_changed("status"):
			emit("rfi.status_changed", self)


def emit_overdue():
	"""Scheduler (daily): one ``rfi.overdue`` per overdue RFI per day (the date is the version)."""
	for name in frappe.get_all("RFI", filters={"status": "Issued", "due_date": ["<", today()]}, pluck="name"):
		emit("rfi.overdue", doctype="RFI", name=name, version=today())
