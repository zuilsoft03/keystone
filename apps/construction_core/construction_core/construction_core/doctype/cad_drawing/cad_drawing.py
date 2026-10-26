# Copyright (c) 2026, Construction Workspace and contributors
"""CAD Drawing (P1-16, P1-18, D-099): one DXF file, or one page of a PDF, of a project, measured in the takeoff viewer.
A DXF is read by ``takeoff.dxf`` into geometry; a PDF page by ``takeoff.pdf`` into its size only (the browser draws
the page). The file must belong to the same project; it becomes a private project file."""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from construction_core.takeoff.dxf import DXFError, parse
from construction_core.takeoff.pdf import PDFError, page_geometry


class CADDrawing(Document):
	def validate(self):
		if self.is_new() or self.has_value_changed("file") or not self.geometry:
			self._read_file()

	def _read_file(self):
		ext = (self.file or "").lower().rsplit(".", 1)[-1]
		if ext not in ("dxf", "pdf"):
			frappe.throw(_("Attach a .dxf file (export DWG drawings as DXF first) or a .pdf"))
		self.source = ext.upper()
		name = frappe.db.get_value("File", {"file_url": self.file}, "name", order_by="creation desc")
		if not name:
			frappe.throw(_("The attached file was not found"))
		f = frappe.get_doc("File", name)
		if f.cc_project and f.cc_project != self.project:
			frappe.throw(_("The file belongs to another project"))
		if not f.cc_project and f.owner != frappe.session.user:
			# Taking a file into the project shows it to every member: only its uploader may do that.
			frappe.throw(_("Attach a drawing you uploaded yourself, or one already in this project"), frappe.PermissionError)
		f.check_permission("read")
		try:
			if self.source == "PDF":
				self.page = cint(self.page) or 1
				geo = page_geometry(f.get_content(), self.page)
			else:
				geo = parse(f.get_content())
		except (DXFError, PDFError) as e:
			frappe.throw(_("The {0} could not be read: {1}").format(self.source, str(e)))
		self.geometry = json.dumps(geo, separators=(",", ":"))
		self.units, self.entity_count = geo["units"], geo["count"]
		self.layers = "\n".join(geo["layers"])
		if not self.calibrated:
			self.unit_to_m = geo["unit_to_m"] or self.unit_to_m
		if not f.cc_project or not f.is_private:
			# The drawing makes its file a private file of the project (D-086), so project rules govern it. A real
			# save, not db_set: File moves a public file into the private folder when is_private changes.
			f.cc_project, f.is_private = self.project, 1
			f.save(ignore_permissions=True)  # the uploader's own file (checked above)
			self.file = f.file_url  # now under /private/files/; the old public URL no longer exists
