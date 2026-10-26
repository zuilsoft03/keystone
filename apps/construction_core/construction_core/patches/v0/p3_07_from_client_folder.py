"""P3-07 (D-140, D-158): every project gets the folders its clients' files land in, 06_Client/From client and
06_Client/Discussion files (and 06_Client itself on a template without it). The folder map is extended in place;
create_workspace is not re-run, since it would show again any folder the team hid from clients."""

import json

import frappe

from construction_core.workspace import ensure_client_folders


def execute():
	for name in frappe.get_all("Workspace Config", pluck="name"):
		cfg = frappe.get_doc("Workspace Config", name)
		folders = json.loads(cfg.folders or "{}")
		if "" not in folders:
			continue  # no tree yet: create_workspace adds the folders when it makes one
		new = ensure_client_folders(name, folders)
		if new != folders:
			cfg.folders = json.dumps(new, sort_keys=True)
			cfg.flags.cc_system = True  # the folder map is server-set (WorkspaceConfig.validate)
			cfg.save(ignore_permissions=True)  # a system migration, not a user's change
