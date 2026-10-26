"""P3-82 (approvals design §14.5): the route doctypes exist before anything reads them, and the new statuses (In
internal review on Approval Request and Client Decision) are in their options. Nothing to backfill: no route means
today's behaviour."""

import frappe


def execute():
	for doctype in ("approval_route_step", "approval_route", "approval_route_version", "approval_request",
			"client_decision"):
		frappe.reload_doc("construction_core", "doctype", doctype)
