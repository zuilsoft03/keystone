# Copyright (c) 2026, Construction Workspace and contributors
"""Approval Route (approvals design §14.2; P3-82): one record kind's internal steps. Each save is checked, appends an
Approval Route Version and rings every Construction Manager (approvals.routes); routes are never deleted (no role may)."""

from frappe.model.document import Document


class ApprovalRoute(Document):
	def validate(self):
		from construction_core.approvals import routes  # here: routes loads the ledger

		routes.check_route(self)

	def on_update(self):
		from construction_core.approvals import routes

		routes.route_saved(self)

	def on_trash(self):
		from construction_core.approvals import log

		log.refuse()  # a route is emptied, never deleted: its versions say what each request ran
