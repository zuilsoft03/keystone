"""P3-22 (R-13; D-193, D-213, D-239): the privacy notice's version, the privacy contact, and erasure.

The join page shows the notice the owner approved in R-13 (its text lives in the shell's join page, flow.js
consentText); VERSION names it, and every consent records it (join imports it as CONSENT_VERSION). The privacy contact
is Firm Settings' (P3-51), else the site config `cc_privacy_email`. Rights requests come by email to that contact
(Frappe's own request forms are off, D-197); a System Manager answers an erasure with `erase`, from the console (RUNBOOK §11). P3-81 (approvals §4.8,
§6 "Erase requests against legal claims"): approval evidence is kept for legal claims (RA 10173 Sec 11(e)); the request
is recorded in each project's chain and the person is told what was kept and why.
"""

import json

import frappe
from frappe import _
from frappe.utils import escape_html, formatdate, nowdate

VERSION = "2026-10-12"  # the R-13 summary (D-213); a new text gets a new version, and old consents keep theirs


def contact() -> str:
	"""P3-51 (D-344, T7): Firm Settings' privacy contact, else site config cc_privacy_email (D-218), else "". The one
	firm detail outsiders see: the join and sign-in pages and the erasure reply read it here."""
	stored = ""
	if frappe.db.exists("DocType", "Firm Settings"):  # during a migrate, before the doctype exists
		stored = frappe.db.get_single_value("Firm Settings", "privacy_email", cache=False)
	return (stored or frappe.conf.get("cc_privacy_email") or "").strip()[:120]


def erase(person: str) -> dict:
	"""Remove our onboarding records of one person: their Client Profile, the invitations bound to their address and
	their requests on open links. Their name and email stay in the project records (D-193); their account, if any, is
	turned off or deleted in Desk. Their approval evidence is kept (Sec 11(e)): each project whose chain names them gets
	an ``erase_request_received`` event, and they get a reply saying what was kept and why. System Manager only; not
	whitelisted (the console, RUNBOOK §11)."""
	frappe.only_for("System Manager")
	email = (frappe.db.get_value("User", person, "email") or person or "").strip().lower()
	account = frappe.db.get_value("User", person, "name") or frappe.db.get_value("User", {"email": email}, "name")
	if not email:
		frappe.throw(_("Give an account or an email address."))
	profiles = frappe.get_all("Client Profile", filters={"account": account or "\0"}, pluck="name")
	for name in profiles:
		frappe.delete_doc("Client Profile", name, force=True, ignore_permissions=True)
	bound = frappe.get_all("Access Invite", filters={"email": email}, pluck="name")
	rows = frappe.get_all("Access Request", filters={"email": email, "parenttype": "Access Invite"}, pluck="name")
	mails = frappe.get_all("Email Queue", filters={"reference_doctype": "Access Invite", "reference_name": ("in", bound or [""])},
		pluck="name") + frappe.get_all("Email Queue", filters={"reference_doctype": "Access Request",
		"reference_name": ("in", rows or [""])}, pluck="name")
	if mails:  # the queue keeps the address as a recipient even after redacting the message
		frappe.db.delete("Email Queue Recipient", {"parent": ("in", mails)})
		frappe.db.delete("Email Queue", {"name": ("in", mails)})
	if bound:
		frappe.db.delete("Access Request", {"parenttype": "Access Invite", "parent": ("in", bound)})
		frappe.db.delete("Access Invite", {"name": ("in", bound)})
	if rows:
		frappe.db.delete("Access Request", {"name": ("in", rows)})
	if account:
		frappe.db.sql("update `tabAccess Request` set account = null where account = %s", account)
		frappe.db.sql("update `tabAccess Invite` set account = null where account = %s", account)  # audit S2
	if account:  # never a record naming an address that has no account: that would keep what was erased
		frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "User",
			"reference_name": account,
			"content": f"Onboarding records erased on request, by {frappe.session.user}"}).insert(ignore_permissions=True)
	projects = _approval_projects({account, email} - {None, ""})
	if projects:
		_keep_approvals(projects, email)
	return {"profiles": len(profiles), "invites": len(bound), "requests": len(rows), "approval_projects": len(projects)}


def _approval_projects(names: set) -> list[str]:
	"""The projects whose chain names the person: as an event's actor, or as a designated approver (a request's
	deciders are its project's approvers)."""
	projects = set(frappe.get_all("Approval Event", filters={"actor": ("in", list(names))}, pluck="project",
		distinct=True))
	for project, text in frappe.get_all("Approval Event", filters={"kind": "designation"}, fields=["project", "canonical"],
			as_list=True):
		if project not in projects and json.loads(text)["body"].get("user") in names:
			projects.add(project)
	return sorted(projects)


def _keep_approvals(projects: list[str], email: str) -> None:
	"""One ``erase_request_received`` event per project (the date only: no personal data beyond what the chain holds),
	then the reply saying what was kept and why."""
	from construction_core.approvals import log  # here: the approvals modules import onboarding
	from construction_core.onboarding.mail import credit_html

	today_ = nowdate()
	for project in projects:
		log.append_event(project, "erase_request_received", body={"note": "request received", "on": today_})
	ask = contact()
	html = "<p>" + "</p><p>".join(escape_html(line) for line in (
		_("We received your request to erase your personal data on {0}, and removed our onboarding records of you.")
			.format(formatdate(today_)),
		_("We keep your approval records: each answer you gave, your signatures, and the device detail recorded with "
			"each answer (the network address, the browser and device type, and the location if you shared it)."),
		_("The law lets us keep them to establish or defend legal claims (Data Privacy Act, RA 10173 Sec 11(e)). They "
			"are deleted when each approval request's retention period ends."),
		_("Questions: write to {0}.").format(ask) if ask else _("Questions: reply to this email."),
	)) + "</p>" + credit_html()
	frappe.sendmail(recipients=[email], subject=_("Your erasure request: what we keep"), message=html,
		add_unsubscribe_link=0)
