"""Frappe's Desk form calls are for the project team only (P3-04 audit, D-168; DR-6).

``frappe.desk.form.load.getdoc`` and ``get_docinfo`` return a record's activity panel with it: its Version rows (every
changed field, internal and permlevel-1/2 values included, since Construction Project tracks changes), its Desk
comments and the names of its attachments. A client may read some records (their project, a shared RFI), so through
these calls they read that history too, although Version and Comment themselves are refused to them. Clients use the
portal (portal_api, discuss.api) and never need Desk, so these calls refuse anyone who is not a System User. Follow
digests are refused the same way: they mail a record's changes. So is v16's activity timeline (frappe.desk.form.activity),
which returns the same comments, attachment names and changes (P3-04 audit re-check), and Desk's comment and
attachment helpers: a client could post a Desk comment stamped with a staff member's email (P3-04 follow-up). And
``linked_with.get``: its ``hidden_count`` tells how many linked rows the caller may not read, such as a Client thread's
staff-only notes or a project's Internal threads (P3-63 audit, D-412).

``override_whitelisted_methods`` (hooks.py) routes /api/method and /api/v2/method calls here; Frappe's own internal
calls (getdoc calling get_docinfo) are unaffected, and getdoc is refused first.
"""

import frappe
from frappe import _
from frappe.desk.form import activity, document_follow, linked_with as linked, load, utils

from construction_core.permissions import _bypass


def _team_only():
	user = frappe.session.user
	if user == "Guest" or frappe.get_cached_value("User", user, "user_type") != "System User":
		raise frappe.PermissionError(_("Not available"))


@frappe.whitelist()
def getdoc(doctype: str, name: str | int):
	_team_only()
	out = load.getdoc(doctype, name)
	_drop_binned(frappe.response.get("docinfo"))
	return out


@frappe.whitelist()
def linked_with(doctype: str, docname: str):
	_team_only()
	found = linked.get(doctype, docname)
	if not _bypass(frappe.session.user):
		# P3-68 audit C6: a type the caller cannot read is left out, so its hidden_count tells nothing (who voted in
		# an anonymous poll, by counting a User's Discuss Poll Vote rows)
		found = {dt: v for dt, v in found.items() if frappe.has_permission(dt, "read")}
	return found


@frappe.whitelist()
def get_docinfo(doc=None, doctype: str | None = None, name: str | int | None = None):
	_team_only()
	out = load.get_docinfo(doc, doctype, name)
	_drop_binned(frappe.response.get("docinfo"))
	return out


def _drop_binned(docinfo) -> None:
	"""P3-68 audit S1: files in the bin leave a record's attachment list (a removed message's chat files with them)
	for everyone but System Managers."""
	if not docinfo or not docinfo.get("attachments") or _bypass(frappe.session.user):
		return
	names = [a.get("name") for a in docinfo["attachments"] if a.get("name")]
	binned = set(frappe.get_all("File", filters={"name": ["in", names], "cc_trashed": 1}, pluck="name")) if names else set()
	docinfo["attachments"] = [a for a in docinfo["attachments"] if a.get("name") not in binned]


@frappe.whitelist()
def get_filtered_attachments(dt: str, dn: str | int, filters: str):
	_team_only()
	return load.get_filtered_attachments(dt, dn, filters)


@frappe.whitelist()
def get_communications(doctype: str, name: str | int, start: str | int = 0, limit: str | int = 20):
	_team_only()
	return load.get_communications(doctype, name, start, limit)


@frappe.whitelist()
def get_activity_timeline(doctype: str, name: str | int, visible_types=None):
	_team_only()
	return activity.get_activity_timeline(doctype, name, visible_types)


@frappe.whitelist()
def get_more_email_activities(doctype: str, name: str | int, start: int):
	_team_only()
	return activity.get_more_email_activities(doctype, name, start)


@frappe.whitelist()
def get_more_milestone_activities(doctype: str, name: str | int, start: int):
	_team_only()
	return activity.get_more_milestone_activities(doctype, name, start)


@frappe.whitelist(methods=["POST", "PUT"])
def add_comment(reference_doctype: str, reference_name: str, content: str, comment_email: str, comment_by: str):
	_team_only()
	return utils.add_comment(reference_doctype, reference_name, content, comment_email, comment_by)


@frappe.whitelist()
def update_comment(name: str | int, content: str):
	_team_only()
	return utils.update_comment(name, content)


@frappe.whitelist()
def update_comment_publicity(name: str, publish: bool):
	_team_only()
	return utils.update_comment_publicity(name, publish)


@frappe.whitelist(methods=["DELETE", "POST"])
def remove_attach():
	_team_only()
	return utils.remove_attach()


@frappe.whitelist()
def follow_document(doctype: str, doc_name: str):
	_team_only()
	return document_follow.follow_document(doctype, doc_name)


@frappe.whitelist()
def update_follow(doctype: str, doc_name: str, following: bool | str):
	_team_only()
	return document_follow.update_follow(doctype, doc_name, following)
