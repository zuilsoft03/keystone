"""P3-77 (D-429): existing sites get the permission types request_client_approval and record_paper_approval, as new
sites do."""

from construction_core.setup.install import ensure_permission_types


def execute():
	ensure_permission_types()
