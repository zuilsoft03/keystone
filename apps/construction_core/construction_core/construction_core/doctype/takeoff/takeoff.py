# Copyright (c) 2026, Construction Workspace and contributors
"""Takeoff (P1-16, D-099): named measurements on one drawing. Quantities are always computed here from the picked
points and the drawing's scale; a quantity sent by the browser is ignored."""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from construction_core.takeoff.dxf import polygon_area, polyline_length

UNITS = {"Length": "m", "Area": "m²", "Count": "pcs"}
MAX_POINTS = 20_000


class Takeoff(Document):
	def validate(self):
		if self.kind not in UNITS:
			frappe.throw(_("Measure must be Length, Area or Count"))
		self.project = frappe.db.get_value("CAD Drawing", self.drawing, "project")
		scale = flt(frappe.db.get_value("CAD Drawing", self.drawing, "unit_to_m"))
		if self.kind != "Count" and not scale:
			frappe.throw(_("Calibrate the drawing first: its units are unknown"))
		self.unit = UNITS[self.kind]
		total = 0.0
		for row in self.items:
			pts = _points(row.points, row.idx)
			if self.kind == "Length":
				if len(pts) < 4:
					frappe.throw(_("Row {0}: a length needs at least two points").format(row.idx))
				row.quantity = polyline_length(pts) * scale
			elif self.kind == "Area":
				if len(pts) < 6:
					frappe.throw(_("Row {0}: an area needs at least three points").format(row.idx))
				row.quantity = polygon_area(pts) * scale * scale
			else:
				row.quantity = len(pts) // 2
			total += row.quantity
		self.total = total


def _points(raw, idx):
	try:
		pts = json.loads(raw or "[]")
	except ValueError:
		frappe.throw(_("Row {0}: the points could not be read").format(idx))
	if not isinstance(pts, list) or len(pts) % 2 or len(pts) > 2 * MAX_POINTS or not all(
			isinstance(v, int | float) and abs(v) < 1e12 for v in pts):
		frappe.throw(_("Row {0}: the points could not be read").format(idx))
	return [float(v) for v in pts]
