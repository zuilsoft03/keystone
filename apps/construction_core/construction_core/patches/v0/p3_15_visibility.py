"""P3-15 (R-13; D-206, D-207): Contact and Address for System Managers only; `enabled` guarded, not hidden."""

from construction_core.accounts import guard
from construction_core.accounts.visibility import restrict_contacts


def execute():
	restrict_contacts()
	guard.apply_property_setters()  # D-207: `enabled` back at permlevel 0, refused by guard_enabled instead
