"""P1-20 (D-104): our roles exist before the doctypes that name them are synced."""

from construction_core.setup.install import ensure_roles


def execute():
	ensure_roles()
