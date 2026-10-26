"""P3-20 (R-13; D-190, D-227): the opt-in two-step role, the site switch on with the authenticator app."""

from construction_core.accounts import two_step


def execute():
	two_step.setup()
