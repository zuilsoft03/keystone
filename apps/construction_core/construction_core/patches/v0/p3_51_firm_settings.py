"""P3-51 (D-344): an existing site's privacy contact (site config cc_privacy_email) moves into Firm Settings."""

from construction_core.accounts.setup import seed_privacy


def execute():
	seed_privacy()
