"""Printing a Print Format renders its template, which a System Manager authors, with the live Document in the context
(printview.get_rendered_template puts it in args['doc'] and validate_print_permission accepts read). Frappe's own
pdf_body_html (the last pdf_body_html hook, frappe/utils/pdf.py) renders it with no safe-render flag, so a template that
calls doc.db_set(...) or frappe.qb.update(...) wrote a ledger column when a staff member printed the format, blamed on
the printer (P3-76 round 4, bypass-8).

This override renders the same way, inside frappe.utils.jinja's safe-render flag context (safe_render_flags): under it
frappe.qb raises on any write (query_builder.utils.prepare_query, check_safe_sql_query) and the jinja globals are the
restricted ones. LedgerRow.before_change backstops db_set (which runs no SQL through the query builder). Frappe's own
exception handling and signature are kept by calling its function unchanged.
"""

import frappe
from frappe.utils.jinja import safe_render_flags
from frappe.utils.pdf import pdf_body_html as _frappe_pdf_body_html

from construction_core.approvals.log import not_ledger


def pdf_body_html(template, args, **kwargs):
	with safe_render_flags():
		return _frappe_pdf_body_html(template, args, **kwargs)


@frappe.whitelist()
def check_conditions(doctype: str, name: str, conditions: list[str] | str):
	"""Override of the whitelisted ``print_format_generator.check_conditions`` (round 5, D3): any reader sends up to 200
	expressions, evaluated against the live Document, and each one's error is caught, so a write before it stays
	(update_modified, db_set, add_tag). Refused on a ledger doctype; elsewhere evaluated under the safe-render flag, where
	every frappe.qb write (frappe.db.set_value among them) is refused."""
	from frappe.utils import print_format_generator

	doctype = not_ledger(doctype)
	with safe_render_flags():
		return print_format_generator.check_conditions(doctype, name, conditions)
