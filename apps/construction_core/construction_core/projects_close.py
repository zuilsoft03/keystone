"""P3-59 (QG, D-338; firm set-up §4 Stage D, T10-T12): Close project.

Close archives the project's Workspace Config (``archived``, ``closed_on``) and sets the project Completed, through a
save, so its Version starts the approvals' retention clock and preflight refuses new requests and answers. From then
on the project's chat takes no new write from anyone and its clients only read (permissions.project_closed). Partner
reads end at close once partners exist (D-444). The daily job (onboarding.jobs) ends client memberships CLIENT_DAYS
after ``closed_on``.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, today

from construction_core.onboarding import invites
from construction_core.permissions import _bypass, is_client, project_closed

CLIENT_DAYS = 90  # clients read the final documents this long after close (QG)


def _project(project):
	if not isinstance(project, str) or not frappe.db.exists("Construction Project", project):
		raise frappe.DoesNotExistError(_("Not found"))
	doc = frappe.get_doc("Construction Project", project)
	if not frappe.has_permission("Construction Project", "read", doc=doc):
		raise frappe.DoesNotExistError(_("Not found"))  # a project the caller may not read answers like a missing one
	return doc


def closed_state(project: str) -> dict:
	"""For a caller who has read the project already (the portal's payload, the Settings card)."""
	closed = project_closed(project)
	on = frappe.db.get_value("Workspace Config", project, "closed_on") if closed else None
	return {"closed": closed, "closed_on": str(on) if on else None,
		"clients_until": str(add_days(on, CLIENT_DAYS)) if on else None}


@frappe.whitelist(methods=["GET"])
def state(project: str) -> dict:
	_project(project)
	return closed_state(project)


@frappe.whitelist(methods=["POST"])
def close(project: str) -> dict:
	"""The project's Construction Managers (manage_team) and System Managers. Closing twice changes nothing."""
	doc = _project(project)
	if is_client(frappe.session.user) or not (_bypass(frappe.session.user)
			or frappe.has_permission("Construction Project", "manage_team", doc=doc)):
		frappe.throw(_("Only the project's managers can close it"), frappe.PermissionError)
	if not frappe.db.exists("Workspace Config", project):
		frappe.throw(_("This project has no workspace to close"))
	cfg = frappe.get_doc("Workspace Config", project, for_update=True)
	if cfg.archived:
		return closed_state(project)
	cfg.update({"archived": 1, "closed_on": today()})
	cfg.flags.cc_closing = True  # the one save that may set them (WorkspaceConfig.validate)
	cfg.save(ignore_permissions=True)  # the caller was checked above; archived and closed_on are permlevel 1
	if doc.status not in ("Completed", "Cancelled"):
		doc.status = "Completed"
		# a save with its Version (Frappe skips it in tests otherwise): the completion approvals' retention reads
		doc.save(ignore_permissions=True, ignore_version=False)
	# No new client joins a closed project: its open client invitations stop (staff invitations are People's).
	for name in frappe.get_all("Access Invite", filters={"project": project, "kind": "Client", "status": "Active"},
			pluck="name"):
		inv = frappe.get_doc("Access Invite", name, for_update=True)
		inv.update({"status": "Revoked", "revoked_by": frappe.session.user, "revoked_on": now_datetime()})
		invites._unprove(inv)
		inv.save(ignore_permissions=True)
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Construction Project",
		"reference_name": project, "content": f"Project closed, by {frappe.session.user}"}).insert(ignore_permissions=True)
	return closed_state(project)


def end_client_memberships(now=None) -> int:
	"""Daily (T12): CLIENT_DAYS after close the project's clients leave it, through a project save, so their shares go,
	their User Permissions follow and a client with no other project gets ``left_on`` (Construction Project._mark_left)."""
	cutoff = add_days(getdate(now or now_datetime()), -CLIENT_DAYS)
	ended = 0
	# "is set": Frappe's "<=" on a date matches an empty one too
	for project in frappe.get_all("Workspace Config", filters=[["archived", "=", 1], ["closed_on", "is", "set"],
			["closed_on", "<=", cutoff]], pluck="project"):
		point = "cc_close_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(point)
		try:
			doc = frappe.get_doc("Construction Project", project)
			kept = [r for r in doc.users if not (r.user and is_client(r.user))]
			gone = len(doc.users) - len(kept)
			if not gone:
				continue
			doc.set("users", kept)
			doc.save(ignore_permissions=True)
		except Exception:
			frappe.db.rollback(save_point=point)  # one project failing never stops the others
			frappe.log_error(title=f"construction_core: ending client memberships of {project} failed")
			continue
		ended += gone
	return ended
