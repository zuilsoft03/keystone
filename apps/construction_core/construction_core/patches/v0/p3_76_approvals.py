"""P3-76 (D-428): existing sites get the client's read of Approval Request (install.CLIENT_READ) and the ledger's
no-delete rows, as new sites do. No section rows: a project without the "approvals" row keeps it off for clients
(permissions.DEFAULT_OFF)."""

from construction_core.setup.install import CLIENT_ROLE, ensure_no_delete, ensure_read_perm


def execute():
	ensure_read_perm("Approval Request", CLIENT_ROLE)
	ensure_no_delete()
