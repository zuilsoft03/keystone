"""Notification's and Webhook's whitelisted condition previews (P3-76 round 5). A System Manager's rule, unsaved
(run_doc_method), evaluates its condition with frappe.safe_eval against the live preview Document, with
frappe.db.set_value and frappe.qb in its globals and no safe-render flag, and swallows the error: a condition wrote any
row, a ledger row's columns included, whatever the rule's doctype. Extended on both (extend_doctype_class), the preview
evaluates under the safe-render flag, where every frappe.qb write is refused.
"""

import frappe
from frappe.utils.jinja import safe_render_flags


class SafePreview:
	@frappe.whitelist()
	def preview_meets_condition(self, preview_document: str | int):
		with safe_render_flags():
			return super().preview_meets_condition(preview_document)
