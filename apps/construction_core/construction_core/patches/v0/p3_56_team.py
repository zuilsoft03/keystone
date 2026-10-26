"""P3-56 (QD, QE): existing sites get the User field cc_job_title and the permission type manage_team, as new sites do."""

from construction_core.setup.install import ensure_team_setup


def execute():
	ensure_team_setup()
