"""The record sections of the workspace (P2-04): which doctype each shows, its columns and its form fields.

The forms read and save through Frappe's own `frappe.client` calls, so the doctype's permissions, the §2.1
predicate (DR-6) and the controllers' state machines decide every change; this module only describes the screens.
Child tables (attachments, distribution, revisions, BOQ deltas) are edited in Desk.
"""

import frappe

RECORDS = {
	"rfi": {
		"doctype": "RFI",
		"title": "subject",
		"state": "status",
		"controller": "construction_core.construction_core.doctype.rfi.rfi",
		"columns": ["subject", "status", "priority", "due_date", "assigned_to"],
		"fields": ["subject", "question", "priority", "discipline", "assigned_to", "due_date", "cost_impact",
			"schedule_impact", "client_visible", "response", "raised_by", "answered_by", "answered_on"],
	},
	"submittals": {
		"doctype": "Submittal",
		"title": "title",
		"state": "status",
		"controller": "construction_core.construction_core.doctype.submittal.submittal",
		"columns": ["title", "status", "spec_section", "required_by", "reviewer"],
		"fields": ["title", "spec_section", "submittal_type", "reviewer", "required_by", "purchase_order",
			"client_visible", "current_revision"],
	},
	"variations": {
		"doctype": "Variation Order",
		"title": "title",
		"state": "stage",
		"controller": "construction_core.construction_core.doctype.variation_order.variation_order",
		"columns": ["title", "stage", "reason", "revised_contract_sum"],
		"fields": ["title", "reason", "time_extension_days", "description", "client_visible", "original_contract_sum",
			"vo_delta_sum", "revised_contract_sum", "approved_by", "approved_on", "boq_revision"],
	},
	"documents": {
		"doctype": "Project Document",
		"title": "title",
		"state": "status",
		"controller": "construction_core.construction_core.doctype.project_document.project_document",
		"columns": ["document_number", "title", "revision", "status", "discipline"],
		"fields": ["document_number", "revision", "title", "discipline", "design_stage", "author", "lead_reviewer",
			"client_approval_required", "client_visible", "document_file", "approved_revision_hash", "supersedes"],
	},
}


def field_meta(meta, fieldname: str) -> dict:
	df = meta.get_field(fieldname)
	options = (df.options or "") if df.fieldtype in ("Select", "Link") else ""
	return {
		"fieldname": df.fieldname,
		"label": df.label,
		"fieldtype": df.fieldtype,
		"options": [o for o in options.split("\n")] if df.fieldtype == "Select" else options,
		"reqd": int(df.reqd or 0),
		"read_only": int(df.read_only or 0),
	}


def form_meta(section: str) -> dict:
	spec = RECORDS[section]
	meta = frappe.get_meta(spec["doctype"])
	state = meta.get_field(spec["state"])
	states = [s for s in (state.options or "").split("\n") if s]
	transitions = frappe.get_attr(spec["controller"] + ".TRANSITIONS")
	return {
		"section": section,
		"doctype": spec["doctype"],
		"title_field": spec["title"],
		"state_field": spec["state"],
		"states": states,
		"transitions": {s: [t for t in states if t in transitions.get(s, set())] for s in states},
		"columns": [field_meta(meta, f) for f in spec["columns"]],
		"fields": [field_meta(meta, f) for f in spec["fields"]],
	}
