"""Override of the whitelisted ``frappe.email.relink`` (P3-76 round 4, bypass-3). It points a Communication at a
reference by raw SQL, with no Communication hook, so approvals.log.refuse_ledger_reference never sees it. Refuse a
ledger target, by the name the database matches (round 5, D4); otherwise call the original with the stored name.
"""

import frappe

from construction_core.approvals.log import not_ledger


@frappe.whitelist()
def relink(name, reference_doctype=None, reference_name=None):
	from frappe.email import relink as _relink
	return _relink(name, reference_doctype=not_ledger(reference_doctype), reference_name=reference_name)
