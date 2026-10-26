"""P3-22 (R-13; D-193, D-223, D-239): the daily retention job of onboarding; P3-59 (T12) adds the end of a closed
project's client memberships.

It runs daily and catches up on every run: everything is decided by timestamps, so a run that comes late, or after a
missed day, removes what is due and nothing early. A link's expiry never depends on it (the join page checks the
timestamps itself).
"""

import frappe
from frappe.utils import add_days, add_to_date, get_datetime, now_datetime

from construction_core.onboarding import invites
from construction_core.projects_close import end_client_memberships

KEEP_DAYS = 30  # unfinished, run out, declined and cancelled invitations (D-193)
CLIENT_DETAIL_YEARS = 2  # a client's mobile and company after they leave their last project (D-193)


def _ended_on(inv):
	"""When an invitation stopped working, or None while it works or after it was used."""
	if inv.status == "Revoked":
		return get_datetime(inv.revoked_on or inv.modified)
	if inv.status == "Used":
		return None  # the person joined: the invitation records who invited whom
	if invites.effective_status(inv) == "Expired":
		return get_datetime(inv.expires_on)
	return None


def _request_done_on(row):
	if row.status == "Declined":
		return get_datetime(row.decided_on or row.modified)
	if row.status == "Approved" and row.finish_expires_on and get_datetime(row.finish_expires_on) <= now_datetime():
		return get_datetime(row.finish_expires_on)
	return None


def purge_invitations(now=None) -> dict:
	now = get_datetime(now or now_datetime())
	cutoff = add_days(now, -KEEP_DAYS)
	deleted, rows = 0, 0
	for name in frappe.get_all("Access Invite", pluck="name"):
		inv = frappe.get_doc("Access Invite", name)
		ended = _ended_on(inv)
		joined = [r for r in inv.requests if r.status == "Joined"]
		if ended and ended <= cutoff and not joined:
			frappe.db.sql("update `tabClient Profile` set joined_from = null where joined_from = %s", name)
			frappe.db.delete("Access Request", {"parenttype": "Access Invite", "parent": name})
			frappe.db.delete("Access Invite", {"name": name})
			deleted += 1
			continue
		for r in inv.requests:
			done = _request_done_on(r)
			if r.status != "Joined" and ((ended and ended <= cutoff) or (done and done <= cutoff)):
				frappe.db.delete("Access Request", {"name": r.name})
				rows += 1
	# A Joined row is the record of who invited whom; the person's mobile and company live on their Client Profile,
	# which the 2-year rule clears, so the row never keeps a copy (P3-22 audit M1).
	frappe.db.sql("""update `tabAccess Request` set mobile_no = null, company_name = null where status = 'Joined'
		and (ifnull(mobile_no, '') != '' or ifnull(company_name, '') != '')""")
	return {"invites": deleted, "requests": rows}


def clear_client_details(now=None) -> int:
	"""Mobile and company go 2 years after a client left their last project; name and email stay (D-193)."""
	now = get_datetime(now or now_datetime())
	cutoff = add_to_date(now, years=-CLIENT_DETAIL_YEARS).date()
	# One explicit query: filters with or_filters also matched profiles with no left_on (P3-22 test).
	names = [r[0] for r in frappe.db.sql("""select name from `tabClient Profile` where left_on is not null
		and left_on <= %s and (ifnull(mobile_no, '') != '' or ifnull(company_name, '') != '')""", cutoff)]
	for name in names:
		frappe.db.set_value("Client Profile", name, {"mobile_no": None, "company_name": None}, update_modified=False)
	return len(names)


def purge_mail(now=None) -> int:
	"""A failed or stuck onboarding mail would keep its code or link (Frappe redacts only after sending, D-223)."""
	now = get_datetime(now or now_datetime())
	queue = frappe.qb.DocType("Email Queue")
	base = (queue.reference_doctype.isin(["Access Invite", "Access Request"]))
	failed = base & (queue.status == "Error") & (queue.modified <= add_days(now, -1))
	stuck = base & queue.status.isin(["Not Sent", "Sending", "Partially Sent"]) & (queue.creation <= add_days(now, -3))
	names = [r[0] for r in frappe.qb.from_(queue).select(queue.name).where(failed | stuck).run()]
	if names:
		frappe.db.delete("Email Queue Recipient", {"parent": ("in", names)})
		frappe.db.delete("Email Queue", {"name": ("in", names)})
	return len(names)


def daily():
	"""scheduler_events daily (D-239). Each part commits on its own, so one failing never undoes the others."""
	for part in (purge_invitations, end_client_memberships, clear_client_details, purge_mail):
		try:
			part()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"construction_core: onboarding retention {getattr(part, '__name__', part)} failed")
