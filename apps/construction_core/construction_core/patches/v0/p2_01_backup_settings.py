"""P2-01: Backup Settings starts with its defaults (off-host copies on, 30 days)."""

from construction_core.backups import ensure_defaults


def execute():
	ensure_defaults()
