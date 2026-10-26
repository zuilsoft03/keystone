"""Workspace counts over realtime (ARCHITECTURE §4, DR-8, D-029).

Counts go to each project member's own user room, never to a ``doctype:`` room. They don't go to the Project's
document room either: clients may read the Project, and staff counts include records clients may not see. A client
gets counts of the records it may read only. Punch items (D-070) are counted once their doctype exists (P2).
"""

import frappe

from construction_core.permissions import client_portal_open, is_client

EVENT = "cc_workspace_counts"
# count key -> (doctype, open-state field, open value)
COUNTED = {
	"rfi_open": ("RFI", "status", "Issued"),
	"submittal_open": ("Submittal", "status", "Under Review"),
	"vo_open": ("Variation Order", "stage", "Change Order Request"),
}
COUNTED_DOCTYPES = {dt for dt, _f, _v in COUNTED.values()}


def counts_for(project: str, user: str) -> dict:
	client = is_client(user)
	counts = {}
	for key, (doctype, field, value) in COUNTED.items():
		filters = {"project": project, field: value}
		if client:
			filters["client_visible"] = 1  # no open state is a client-hidden one (permissions.CLIENT_HIDDEN_STATE)
		counts[key] = frappe.db.count(doctype, filters)
	return counts


def members(project: str) -> list[str]:
	return frappe.get_all("Project Member", filters={"parenttype": "Construction Project", "parent": project}, pluck="user")


def recompute_counts(project: str):
	"""Publish each member's counts to that member's user room; clients get none while the portal is off."""
	portal_open = client_portal_open(project)
	for user in members(project):
		if not portal_open and is_client(user):
			continue
		frappe.publish_realtime(EVENT, {"project": project, "counts": counts_for(project, user)}, user=user,
			after_commit=True)


def on_change(doc, method=None):
	"""doc_events for the counted doctypes: one deduplicated job per project."""
	project = doc.get("project")
	if not project:
		return
	if frappe.flags.cc_events_sync:
		recompute_counts(project)
		return
	frappe.enqueue("construction_core.core.counts.recompute_counts", queue="short", project=project,
		job_id=f"cc-counts-{project}", deduplicate=True, enqueue_after_commit=True)


@frappe.whitelist()
def get_counts(project: str) -> dict:
	"""The session user's counts for a project it may read (initial load; later updates come over realtime)."""
	frappe.get_doc("Construction Project", project).check_permission("read")
	return counts_for(project, frappe.session.user)
