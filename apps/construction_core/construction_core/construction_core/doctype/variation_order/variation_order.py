# Copyright (c) 2026, Construction Workspace and contributors
"""Variation Order (ARCHITECTURE §6.5, §9.3).

Potential Change -> Change Order Request -> Approved Change (or Rejected). Approval needs the ``approve_variation``
Permission Type. Approval never mutates a BOQ: it creates a new BOQ revision (``is_baseline=0``) from the latest
approved revision with the deltas applied, and approves it under ``approve_variation`` alone (D-092).
``revised_contract_sum`` = baseline + Σ approved VO deltas. Approved and Rejected variations are final; an approved
one cannot be deleted. Approval locks the project row: a concurrent second approval fails with a retry message, and
no delta is lost.
"""

import math
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from construction_core.construction_core.doctype.boq.boq import baseline_sum, carry_origins, line_project, origin
from construction_core.core.events import emit
from construction_core.permissions import _bypass

MAX_AMOUNT = 10**11  # well inside the Currency column (decimal 21,9), so a bad entry is a message, not a DB error
FINAL = {"Approved Change", "Rejected"}

TRANSITIONS = {
	"Potential Change": {"Change Order Request", "Rejected"},
	"Change Order Request": {"Approved Change", "Rejected", "Potential Change"},
	"Approved Change": set(),
	"Rejected": set(),
}


def approved_delta_sum(project: str, exclude: str | None = None) -> float:
	filters = {"project": project, "stage": "Approved Change"}
	if exclude:
		filters["name"] = ["!=", exclude]
	return sum(flt(v) for v in frappe.get_all("Variation Order", filters=filters, pluck="vo_delta_sum"))


def latest_approved_boq(project: str, for_update: bool = False) -> str | None:
	return frappe.db.get_value("BOQ", {"project": project, "status": "Approved"}, "name", order_by="revision desc",
		for_update=for_update)


@contextmanager
def _concurrent_approval():
	try:
		yield
	except frappe.QueryDeadlockError:
		frappe.throw(_("Another variation of this project was approved at the same moment: reload and approve again"),
			title=_("Approved concurrently"))


def _origin_of(line_name: str) -> str:
	return frappe.db.get_value("BOQ Line", line_name, "origin_line") or line_name


class VariationOrder(Document):
	def before_insert(self):
		if self.stage != "Potential Change":
			frappe.throw(_("A new variation starts as a Potential Change"))

	def validate(self):
		before = self.get_doc_before_save()
		if before and before.stage in FINAL and not _bypass(frappe.session.user):
			frappe.throw(_("An approved or rejected variation is final: raise a new variation instead"))
		if (self.decision_request or "") != ((before.decision_request if before else "") or "") \
				and not self.flags.cc_decision:  # P3-77 (§3.3): only Make the variation names a Decision's approval
			frappe.throw(_("A variation names a Decision's approval only when it is made from it"), frappe.PermissionError)
		approving = self.stage == "Approved Change" and (not before or before.stage != self.stage)
		if approving:
			# Serialise approvals per project. MariaDB refuses a locking read of a row changed after this
			# transaction's snapshot (error 1020), so a concurrent second approval fails cleanly and is retried.
			with _concurrent_approval():
				frappe.db.get_value("Construction Project", self.project, "name", for_update=True)
		self._compute()
		if before and before.stage != self.stage:
			if self.stage not in TRANSITIONS.get(before.stage, set()):
				frappe.throw(_("A variation cannot move from {0} to {1}").format(_(before.stage), _(self.stage)),
					title=_("Invalid stage"))
			if self.stage == "Approved Change":
				frappe.has_permission("Variation Order", "approve_variation", doc=self, throw=True)
				if not latest_approved_boq(self.project):
					frappe.throw(_("Approve the project's baseline BOQ before approving a variation"))
				self.approved_by = frappe.session.user
				self.approved_on = now_datetime()

	def _compute(self):
		lines = self._boq_lines()
		for d in self.deltas:
			if not (math.isfinite(flt(d.qty_delta)) and math.isfinite(flt(d.rate_delta))):
				frappe.throw(_("Row {0}: quantity and rate must be numbers").format(d.idx))
			if d.boq_line:
				key = _origin_of(d.boq_line) if line_project(d.boq_line) == self.project else None
				if key not in lines:
					frappe.throw(_("Row {0}: BOQ line {1} is not in the project's current BOQ").format(d.idx, d.boq_line))
				q, r = lines[key]
				new_q, new_r = q + flt(d.qty_delta), r + flt(d.rate_delta)
			else:
				q = r = 0.0  # a new item: qty_delta and rate_delta are its quantity and rate
				new_q, new_r = flt(d.qty_delta), flt(d.rate_delta)
			if new_q < 0 or new_r < 0:
				frappe.throw(_("Row {0}: the resulting quantity and rate cannot be negative").format(d.idx))
			if new_q * new_r >= MAX_AMOUNT:
				frappe.throw(_("Row {0}: the resulting amount is too large").format(d.idx))
			# P3-77 (C4): stored at the field's precision, so an approval's text never rounds two amounts onto one
			d.amount_delta = flt(new_q * new_r - q * r, d.precision("amount_delta"))
		self.vo_delta_sum = flt(sum(flt(d.amount_delta) for d in self.deltas), self.precision("vo_delta_sum"))
		if abs(self.vo_delta_sum) >= MAX_AMOUNT:
			frappe.throw(_("The variation total is too large"))
		self.original_contract_sum = baseline_sum(self.project)
		approved_others = approved_delta_sum(self.project, exclude=self.name)
		mine = self.vo_delta_sum if self.stage == "Approved Change" else 0
		self.revised_contract_sum = self.original_contract_sum + approved_others + mine

	def _boq_lines(self) -> dict:
		boq = latest_approved_boq(self.project)
		if not boq:
			return {}
		return {origin(l): (flt(l.qty), flt(l.rate)) for l in frappe.get_doc("BOQ", boq).lines}

	def on_trash(self):
		if self.stage == "Approved Change" and not _bypass(frappe.session.user):
			frappe.throw(_("An approved variation cannot be deleted"), frappe.PermissionError)

	def on_update(self):
		from construction_core.approvals import subjects  # here: approvals loads the ledger

		subjects.check(self)  # P3-77: the client's approval, on the saved terms (§3.10, §3.11)
		if not self.has_value_changed("stage"):
			return
		if self.stage == "Approved Change":
			self._create_boq_revision()
			subjects.on_variation_approved(self)
		emit("vo.stage_changed", self)

	def _create_boq_revision(self):
		with _concurrent_approval():
			source = frappe.get_doc("BOQ", latest_approved_boq(self.project, for_update=True))
		new = frappe.copy_doc(source)
		new.is_baseline = 0
		new.title = _("{0} + {1}").format(source.title or source.name, self.name)
		carry_origins(source, new)
		by_origin = {l.origin_line: l for l in new.lines}
		for d in self.deltas:
			if d.boq_line:
				line = by_origin[_origin_of(d.boq_line)]
				line.qty = flt(line.qty) + flt(d.qty_delta)
				line.rate = flt(line.rate) + flt(d.rate_delta)
			else:
				new.append("lines", {"description": d.description, "qty": d.qty_delta, "rate": d.rate_delta, "uom": d.uom})
		# ignore_permissions: the revision is a consequence of this approval, which the approver was allowed.
		new.insert(ignore_permissions=True)
		new.status = "Approved"
		new.flags.ignore_permissions = True
		new.flags.cc_approved_by_variation = self.name  # D-092: approve_variation covers this revision
		new.save()
		self.db_set("boq_revision", new.name)
