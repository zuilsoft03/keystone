"""P3-40 (D-288): Construction Staff read, but no longer change, a project's permlevel-2 fields (the site place and
coordinates, the estimated costing, the default retention, VAT and withholding and the internal notes)."""

import frappe

from construction_core.setup.install import ensure_read_only_levels


def execute():
	ensure_read_only_levels()
	frappe.clear_cache(doctype="Construction Project")
