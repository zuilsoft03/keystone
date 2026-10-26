"""Takeoff API (P1-16, P1-18, D-099): the drawing's geometry, calibration, saving takeoffs, and the Excel export.

Takeoff is staff work (estimating): clients have no access. Quantities are computed by the Takeoff controller from
points in drawing units and the drawing's scale (metres per unit), never taken from the browser.
"""

import json
import math

import frappe
from frappe import _
from frappe.utils import cint, flt

from construction_core.permissions import is_client


def _staff():
	if is_client(frappe.session.user):
		frappe.throw(_("Takeoff is for the project team"), frappe.PermissionError)


def _drawing(name: str, ptype: str = "read"):
	_staff()
	d = frappe.get_doc("CAD Drawing", name)
	d.check_permission(ptype)
	return d


def _takeoffs(drawing: str) -> list:
	rows = frappe.get_list("Takeoff", filters={"drawing": drawing}, fields=["name", "title", "kind", "unit", "total", "color"],
		order_by="creation asc")
	for t in rows:
		t["items"] = [{"name": i.name, "label": i.label, "quantity": i.quantity, "points": json.loads(i.points or "[]")}
			for i in frappe.get_all("Takeoff Item", filters={"parent": t.name, "parenttype": "Takeoff"},
				fields=["name", "label", "quantity", "points"], order_by="idx asc")]
	return rows


@frappe.whitelist()
def drawing(name: str) -> dict:
	d = _drawing(name)
	return {"name": d.name, "title": d.title, "project": d.project, "source": d.source or "DXF", "file": d.file,
		"units": d.units, "unit_to_m": flt(d.unit_to_m),
		"calibrated": cint(d.calibrated), "geometry": json.loads(d.geometry or "{}"), "takeoffs": _takeoffs(d.name),
		"can_edit": d.has_permission("write")}


@frappe.whitelist(methods=["POST"])
def calibrate(name: str, points: str, real_length_m: float | str) -> float:
	"""Set the scale from two picked points and their real distance; every takeoff of the drawing is recomputed."""
	d = _drawing(name, "write")
	pts = json.loads(points) if isinstance(points, str) else points
	if not isinstance(pts, list) or len(pts) != 4:
		frappe.throw(_("Pick two points to calibrate"))
	dist = math.hypot(flt(pts[2]) - flt(pts[0]), flt(pts[3]) - flt(pts[1]))
	real = flt(real_length_m)
	if dist <= 0 or real <= 0 or not math.isfinite(real):
		frappe.throw(_("Pick two different points and enter their real distance"))
	scale = real / dist
	if not (math.isfinite(scale) and 1e-9 <= scale <= 1e6):
		frappe.throw(_("That calibration gives an impossible scale: pick points further apart"))
	d.unit_to_m, d.calibrated = scale, 1
	d.save()
	for t in frappe.get_all("Takeoff", filters={"drawing": name}, pluck="name"):
		frappe.get_doc("Takeoff", t).save()  # recompute with the new scale
	return d.unit_to_m


@frappe.whitelist(methods=["POST"])
def save_takeoff(drawing: str, title: str, kind: str, items: str, takeoff: str | None = None,
		color: str | None = None) -> dict:
	_drawing(drawing)
	rows = json.loads(items) if isinstance(items, str) else items
	if not isinstance(rows, list):
		frappe.throw(_("The measurements could not be read"))
	if takeoff:
		t = frappe.get_doc("Takeoff", takeoff)
		if t.drawing != drawing:
			frappe.throw(_("This takeoff belongs to another drawing"))
		t.title, t.kind = title, kind
		t.color = color or t.color
		t.set("items", [])
	else:
		t = frappe.get_doc({"doctype": "Takeoff", "drawing": drawing, "title": title, "kind": kind,
			"color": color or "#e8590c"})
	for r in rows:
		r = r if isinstance(r, dict) else {}
		t.append("items", {"label": (r.get("label") or "")[:140], "points": json.dumps(r.get("points") or [])})
	t.save() if takeoff else t.insert()
	return {"name": t.name, "total": t.total, "unit": t.unit,
		"items": [{"label": i.label, "quantity": i.quantity} for i in t.items]}


@frappe.whitelist(methods=["POST"])
def delete_takeoff(name: str):
	_staff()
	frappe.delete_doc("Takeoff", name)


def _cell(v):
	# A text cell starting with = + - @ would run as a formula in Excel (formula injection): keep it text.
	return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


@frappe.whitelist()
def export(name: str):
	"""All takeoffs of a drawing as an Excel file: one row per measurement, plus a total per takeoff."""
	from frappe.utils.xlsxutils import make_xlsx

	d = _drawing(name)
	data = [[_("Drawing"), d.title], [_("Scale"), f"{flt(d.unit_to_m):.9g} m per drawing unit"], [],
		[_("Takeoff"), _("Measure"), _("Item"), _("Quantity"), _("Unit")]]
	for t in _takeoffs(d.name):
		for i in t["items"]:
			data.append([t.title, _(t.kind), i["label"] or "", round(flt(i["quantity"]), 4), t.unit])
		data.append([t.title, _("Total"), "", round(flt(t.total), 4), t.unit])
	xlsx = make_xlsx([[_cell(v) for v in row] for row in data], "Takeoff")
	frappe.response["filename"] = f"takeoff-{d.name}.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"
