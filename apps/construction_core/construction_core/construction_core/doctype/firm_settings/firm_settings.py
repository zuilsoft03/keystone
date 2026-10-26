# Copyright (c) 2026, Construction Workspace and contributors
"""Firm Settings (P3-51, P3-52; D-344, D-347): the firm's legal details, privacy contact, default rates and set-up
progress. System Managers only (T7): the wizard's calls in construction_core.accounts.setup, or Desk and REST, which
meet the same checks here. Outsiders see only the privacy contact, through onboarding.privacy.contact()."""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, validate_email_address

CONTROL = re.compile(r"[\u0000-\u0009\u000b-\u001f\u007f]")  # every control character but the line break
RATES = ("default_vat", "default_retention", "default_withholding")


class FirmSettings(Document):
	def validate(self):
		from construction_core.accounts.setup import STATES, STEPS
		from construction_core.onboarding.invites import SEPARATORS

		for field in ("legal_name", "tin", "phone", "address", "privacy_email"):
			value = CONTROL.sub("", self.get(field) or "").strip()
			self.set(field, value[:500] if field == "address" else value.replace("\n", " "))
		self.privacy_email = self.privacy_email.lower()
		if self.privacy_email and (SEPARATORS.search(self.privacy_email)
				or validate_email_address(self.privacy_email) != self.privacy_email):
			frappe.throw(_("Give one valid email address for the privacy contact."))
		for field in RATES:
			if self.get(field) is not None and not 0 <= flt(self.get(field)) <= 100:
				frappe.throw(_("{0} must be between 0 and 100.").format(self.meta.get_label(field)))
		for row in self.steps:
			if row.step not in STEPS or row.state not in STATES:
				frappe.throw(_("Unknown set-up step."))
