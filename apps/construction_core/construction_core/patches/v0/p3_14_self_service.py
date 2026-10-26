"""P3-14 (R-13, D-204): User security fields at System Manager level, User shares only to their own user, and the
sign-in settings pinned."""

from construction_core.accounts import guard, settings


def execute():
	guard.apply_property_setters()
	guard.remove_foreign_user_shares()
	settings.apply()
