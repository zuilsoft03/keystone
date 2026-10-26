"""The approvals preflight (design §3.2, D-429): one check, which the Ask sheet, the request endpoint and the answer path
all run, naming every reason a project cannot take or answer a request now and where each is put right."""

import frappe
from frappe import _
from frappe.utils import cint

from construction_core.approvals import subjects
from construction_core.approvals.api import approvers
from construction_core.permissions import client_portal_open, client_section_open, project_closed

CLOSED = ("Completed", "Cancelled")  # a closed project takes no new request (P3-59)


def preflight(project: str, subject_doctype: str | None = None, subject_name: str | None = None) -> list[dict]:
	"""Each reason as {"key", "reason", "fix"} (``fix``: the place to put it right); none means ready. A subject's own
	checks join the project's."""
	p = frappe.db.get_value("Construction Project", project, ["status", "cc_portal_approvals", "cc_contract_document",
		"cc_contract_date", "cc_contract_clause", "cc_client_legal_name", "cc_client_address"], as_dict=True) \
		if isinstance(project, str) else None
	if not p:
		raise frappe.DoesNotExistError(_("Not found"))
	checks = (
		("site", not frappe.conf.get("cc_approvals_enabled"), _("Approvals are not turned on for this site yet"), "site"),
		("closed", p.status in CLOSED or project_closed(project), _("This project is closed"), "project"),
		("portal_approvals", not cint(p.cc_portal_approvals), _("Portal approvals are off for this project"),
			"approval_settings"),
		("contract", not (p.cc_contract_document and p.cc_contract_date and p.cc_contract_clause),
			_("The contract reference is missing"), "approval_settings"),
		("client_party", not (p.cc_client_legal_name and p.cc_client_address),
			_("The client's legal name and address are missing"), "approval_settings"),
		("evidence_mailbox", not cint(frappe.db.get_single_value("Approval Settings", "evidence_mailbox_confirmed",
			cache=False)), _("The evidence mailbox is not confirmed"), "evidence_mailbox"),
		("approver", not any(approvers(project).values()), _("No approver is set up"), "approvers"),
		("client_access", not (client_portal_open(project) and client_section_open("Approval Request", project)),
			_("Clients cannot open approvals in the portal"), "portal_sections"),
	)
	if subject_doctype:  # the record's own (§3.1): its state, and client visible so its approvers can read the request
		s = subjects.SUBJECTS.get(subject_doctype)
		doc = frappe.get_doc(subject_doctype, subject_name) if s and frappe.db.exists(subject_doctype, subject_name) \
			else None
		if not doc or doc.project != project:
			raise frappe.DoesNotExistError(_("Not found"))
		checks += (
			("record_state", doc.get(s.state) not in s.send, _("This record cannot be sent for approval in its current "
				"state"), "record"),
			("record_visible", subject_doctype != subjects.DECISION and not cint(doc.get("client_visible")),
				_("Clients cannot see this record: turn on Client Visible first"), "record"),
		)
		from construction_core.approvals import routes  # here: routes imports api, which imports this module's

		# P3-82 (§14.2): each internal step that applies needs someone on this project to do it
		why = routes.acknowledging(subject_name) if subject_doctype == subjects.DECISION else ""
		checks += (("record_final", bool(why), why, "record"),)
		checks += tuple(("route_step", True, _("No one on this project can do {0}").format(step), "approval_steps")
			for step in routes.unstaffed(doc))
	return [{"key": key, "reason": reason, "fix": fix} for key, failed, reason, fix in checks if failed]
