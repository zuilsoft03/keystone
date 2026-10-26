# Copyright (c) 2026, Construction Workspace and contributors
"""Construction Project (P1-20, D-104): the project record of the independent core (replaces ERPNext's Project).

Membership is the ``users`` table (Project Member). Access is the §2.1 predicate (permissions.can_access);
the managers change the members (permlevel 1); money and notes are staff-only (permlevel 2, D-097). Its files
are attached to it, so ``max_attachments`` is 0 (no limit).
"""

import frappe
from frappe.model.document import Document
from frappe.utils import today


class ConstructionProject(Document):
	def validate(self):
		_check_site(self)
		if self.is_new():
			_take_firm_rates(self)

	def on_update(self):
		_mark_left(self)

	def on_trash(self):
		# A deleted project ends its clients' memberships too (D-239).
		from construction_core.permissions import is_client

		for row in self.get("users") or []:
			if not row.user or not is_client(row.user):
				continue
			elsewhere = frappe.db.exists("Project Member", {"parenttype": "Construction Project", "user": row.user,
				"parent": ("!=", self.name)})
			profile = frappe.db.get_value("Client Profile", {"account": row.user})
			if profile and not elsewhere:
				frappe.db.set_value("Client Profile", profile, "left_on", today(), update_modified=False)


def _take_firm_rates(doc):
	"""P3-55 (W7): a new project's rates that nobody gave come from Firm Settings; a given 0 stays 0. In validate, not
	before_insert: Frappe resets the permlevel 2 fields a creator cannot write after before_insert."""
	firm = frappe.db.get_singles_dict("Firm Settings")
	for field, source in (("cc_default_vat_pct", "default_vat"), ("cc_default_retention_pct", "default_retention"),
			("cc_default_withholding_pct", "default_withholding")):
		if doc.get(field) is None and firm.get(source) is not None:
			doc.set(field, firm.get(source))


def _check_site(doc):
	"""P3-09 (D-138, D-157): a site location is both coordinates or neither; a 0 counts as missing (an empty Float
	field reads as 0, and 0, 0 is in the sea off Africa); each must be on the globe."""
	from frappe import _
	from frappe.utils import flt

	lat, lng = flt(doc.get("cc_latitude")), flt(doc.get("cc_longitude"))
	if bool(lat) != bool(lng):
		frappe.throw(_("Give both the latitude and the longitude of the site, or neither."))
	if lat and not (-90 <= lat <= 90 and -180 <= lng <= 180):
		frappe.throw(_("The latitude must be between -90 and 90, the longitude between -180 and 180."))


def _mark_left(doc):
	"""P3-22 (D-193, D-239): a client whose last membership ends gets `left_on` on their Client Profile (their mobile
	and company are cleared 2 years later); a client who joins again loses it."""
	from construction_core.permissions import is_client

	before = doc.get_doc_before_save()
	old = {r.user for r in (before.get("users") if before else []) if r.user}
	now = {r.user for r in doc.get("users") or [] if r.user}
	for user in (old - now) | (now - old):
		if not is_client(user):
			continue
		profile = frappe.db.get_value("Client Profile", {"account": user})
		if not profile:
			continue
		member = frappe.db.exists("Project Member", {"parenttype": "Construction Project", "user": user})
		frappe.db.set_value("Client Profile", profile, "left_on", None if member else today(), update_modified=False)
