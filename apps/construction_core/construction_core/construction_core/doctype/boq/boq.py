# Copyright (c) 2026, Construction Workspace and contributors
"""BOQ with revisions (ARCHITECTURE §6.5).

- Revisions, not mutation: an Approved BOQ is immutable. A new revision is a new BOQ; approving it supersedes the
  previous approved revision, except the baseline, which stays the contract reference.
- One baseline per project: the first approved revision unless another is marked ``is_baseline``.
- Progress is never tracked on BOQ lines (it belongs to Progress Billing Line, P4); VOs add delta lines (P1-08).
- Any save that makes a BOQ Approved needs ``approve_boq`` (§2.4), except the revision a variation approval creates
  (D-092). An approved or superseded BOQ cannot be deleted.
"""

import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from construction_core.core.events import emit
from construction_core.permissions import _bypass

LOCKED_FIELDS = ("project", "currency", "is_baseline", "revision")


class BOQ(Document):
	def before_insert(self):
		revisions = frappe.get_all("BOQ", filters={"project": self.project}, pluck="revision")
		last = max([r or 0 for r in revisions], default=0)
		self.revision = int(last) + 1
		self.status = "Draft"
		self.approved_by = self.approved_on = None

	def validate(self):
		before = self.get_doc_before_save()
		if before and before.status in ("Approved", "Superseded"):
			self._check_immutable(before)
		approving = self.status == "Approved" and (not before or before.status != "Approved")
		if approving and not self.flags.cc_approved_by_variation:
			frappe.has_permission("BOQ", "approve_boq", doc=self, throw=True)  # §2.4 Permission Type
		self._keep_origins(before)
		for line in self.lines:
			for f in ("qty", "rate", "retention_pct"):
				if not math.isfinite(flt(line.get(f))):
					frappe.throw(_("Row {0}: {1} must be a number").format(line.idx, f))
			line.amount = flt(line.qty) * flt(line.rate)
		self.total = sum(flt(line.amount) for line in self.lines)
		if self.is_baseline and self.status == "Approved":
			other = frappe.db.get_value(
				"BOQ", {"project": self.project, "is_baseline": 1, "status": ["!=", "Draft"], "name": ["!=", self.name]}
			)
			if other:
				frappe.throw(_("Project {0} already has a baseline BOQ: {1}").format(self.project, other))

	def _keep_origins(self, before):
		"""``origin_line`` is set by the server only (``carry_origins``): a forged lineage would let a VO delta land
		on another line (P1-08 re-audit). Users' rows keep their saved value; new rows have none."""
		if self.flags.cc_carry_origins:
			for line in self.lines:
				if line.origin_line and line_project(line.origin_line) != self.project:
					line.origin_line = None
		else:
			saved = {l.name: l.origin_line for l in before.lines} if before else {}
			for line in self.lines:
				line.origin_line = saved.get(line.name) if line.name else None
		origins = [l.origin_line for l in self.lines if l.origin_line]
		if len(origins) != len(set(origins)):
			frappe.throw(_("Two lines of a BOQ cannot descend from the same line"))

	def _check_immutable(self, before):
		if self.status == "Draft" or (before.status == "Superseded" and self.status != "Superseded"):
			frappe.throw(_("An approved BOQ cannot go back to Draft: create a new revision"))
		changed = [f for f in LOCKED_FIELDS if str(before.get(f) or "") != str(self.get(f) or "")]
		if changed or _lines(before) != _lines(self):
			frappe.throw(_("An approved BOQ is immutable: create a new revision (changed: {0})").format(
				", ".join(changed) or _("lines")), title=_("BOQ is approved"))

	def on_trash(self):
		if self.status in ("Approved", "Superseded") and not _bypass(frappe.session.user):
			frappe.throw(_("An approved BOQ cannot be deleted"), frappe.PermissionError)

	def on_update(self):
		if self.has_value_changed("status") and self.status == "Approved":
			self._on_approved()

	def _on_approved(self):
		self.db_set({"approved_by": frappe.session.user, "approved_on": now_datetime()})
		if not frappe.db.exists("BOQ", {"project": self.project, "is_baseline": 1, "name": ["!=", self.name]}):
			self.db_set("is_baseline", 1)
		for old in frappe.get_all(
			"BOQ",
			filters={"project": self.project, "status": "Approved", "is_baseline": 0, "name": ["!=", self.name]},
			pluck="name",
		):
			frappe.db.set_value("BOQ", old, "status", "Superseded")
			emit("boq.superseded", doctype="BOQ", name=old, version=self.name)
		emit("boq.approved", self)

	@frappe.whitelist()
	def approve(self):
		frappe.has_permission("BOQ", "approve_boq", doc=self, throw=True)  # §2.4 Permission Type
		self.status = "Approved"
		self.save()

	@frappe.whitelist()
	def new_revision(self):
		"""Copy this BOQ into a new Draft revision (revisions, not mutation)."""
		self.check_permission("read")
		new = frappe.copy_doc(self)
		new.is_baseline = 0
		carry_origins(self, new)
		new.insert()
		return new.name


def _lines(doc):
	return [(l.wbs_node, l.cost_code, l.description, l.uom, flt(l.qty), flt(l.rate), flt(l.retention_pct), l.origin_line)
		for l in doc.lines]


def origin(line) -> str:
	return line.origin_line or line.name


def carry_origins(source, copy):
	"""A copied revision's lines keep their lineage (copy_doc keeps the order but renames the rows)."""
	for old, new in zip(source.lines, copy.lines, strict=True):
		new.origin_line = origin(old)
	copy.flags.cc_carry_origins = True


def line_project(line_name: str) -> str | None:
	parent = frappe.db.get_value("BOQ Line", line_name, "parent")
	return frappe.db.get_value("BOQ", parent, "project") if parent else None


def baseline(project: str) -> str | None:
	return frappe.db.get_value("BOQ", {"project": project, "is_baseline": 1, "status": "Approved"})


def baseline_sum(project: str) -> float:
	name = baseline(project)
	return flt(frappe.db.get_value("BOQ", name, "total")) if name else 0.0
