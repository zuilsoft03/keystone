"""Who reads an Approval Request (design §7, D-428): the request's own rule, never its subject's.

Staff read their projects' requests by role (Construction Manager, Construction Staff) inside the project scope. A
client (Construction Client, install.CLIENT_READ) reads one only while all of these hold:

1. they are a member of the project (permissions.project_scoped, can_access: allowed_projects);
2. the project's portal is on (client_portal_open);
3. its "approvals" section is on (CLIENT_SECTION; the section starts off, permissions.DEFAULT_OFF);
4. the request reached the client: it has a ``requested`` event (P3-82, §14.3, §14.5). A Draft, a request In internal
   review and one that left internal review (sent on as a new request, superseded on a change, or voided) never did;
5. its decider party is client.

4 and 5 are ``CLIENT_SQL`` for lists (permissions.CLIENT_ONLY_SQL) and ``client_may_read`` for one record
(permissions.client_may_see), both on server-set columns. The rule never reads the subject's visibility or status, so a
decided request stays readable after its record moves on or is archived. Shares never widen it (validate_share).
"""

import frappe

DOCTYPE = "Approval Request"
HIDDEN = ("Draft", "In internal review")  # never a client's (log.INTERNAL)
REACHED = ("Open", "Approved", "Returned")  # only ever after a requested event (log.TRANSITIONS)
CLIENT_SQL = ("ifnull(`tabApproval Request`.`status`, '') not in ('', 'Draft', 'In internal review')"
	" and `tabApproval Request`.`decider_party` = 'client'"
	" and exists (select 1 from `tabApproval Event` cc_e where cc_e.request = `tabApproval Request`.`name`"
	" and cc_e.kind = 'requested')")


def asked(request: str) -> bool:
	"""Whether the request ever reached the client: its requested event."""
	return bool(request) and bool(frappe.db.exists("Approval Event", {"request": request, "kind": "requested"}))


def client_may_read(doc) -> bool:
	status = doc.get("status") or "Draft"
	return status not in HIDDEN and doc.get("decider_party") == "client" and (
		status in REACHED or asked(doc.get("name")))


def readable(request) -> "frappe.model.document.Document | None":
	"""The request as the caller may read it, or None. Both sides of the rule must let them in: the list as the caller
	(role, project scope, CLIENT_SQL) and the record's own permission (can_access, client_may_see)."""
	if not isinstance(request, str) or not request:
		return None
	try:
		if not frappe.get_list(DOCTYPE, filters={"name": request}, pluck="name", limit=1):
			return None
	except frappe.PermissionError:
		return None  # no role reads requests (a partner, until P3-32)
	doc = frappe.get_doc(DOCTYPE, request)
	return doc if frappe.has_permission(DOCTYPE, "read", doc=doc) else None
