# Copyright (c) 2026, Construction Workspace and contributors
"""Client Profile (P3-16, R-13; D-187, D-209): the client record (name the team sees, mobile, company, consent). System Manager only; the team reads it through construction_core.onboarding.invites.client_details. Never on Project Member (D-105)."""

from frappe.model.document import Document


class ClientProfile(Document):
	pass
