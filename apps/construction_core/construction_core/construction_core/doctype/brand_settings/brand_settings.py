# Copyright (c) 2026, Construction Workspace and contributors
"""Brand Settings (P3-45, D-300): the firm's brand. Written by System Managers only (the Brand page's calls in
construction_core.brand, or Desk and REST, which meet the same checks here); everyone sees it through brand.public()."""

import frappe
from frappe import _
from frappe.model.document import Document

from construction_core import brand


class BrandSettings(Document):
	def validate(self):
		self.company_name = (self.company_name or "").strip()[:80]
		self.main_colour = brand.check_colour(self.main_colour, _("Main colour"), button=True)
		self.panel_colour = brand.check_colour(self.panel_colour, _("Brand panel colour"), button=False)
		if (self.heading_font or "") not in ("", *brand.FONTS):
			frappe.throw(_("Choose one of the listed heading fonts."))
		for field in brand.IMAGES.values():
			brand.check_image(self.get(field) or "", field)

	def on_update(self):
		before = self.get_doc_before_save()
		brand.drop_images(before.as_dict() if before else {}, self)
		brand.clear_cache()
		frappe.db.after_commit.add(brand.clear_cache)  # a reader between now and the commit cached the old row
		frappe.db.after_rollback.add(brand.clear_cache)  # this request may have cached the row it then rolled back
