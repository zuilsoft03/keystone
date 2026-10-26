"""DocumentProvider (D-082): how an office file is opened and saved.

``NullEditor`` is the fallback ONLYOFFICE uses when it is absent or a user is beyond the edit-session limit:
download the file, edit it locally, upload a new version. The ONLYOFFICE provider (``OnlyOfficeEditor``, P1-17)
returns an editor config instead; it is used when the site has an ONLYOFFICE secret (P1-17).
"""

from __future__ import annotations

import frappe

from construction_core.providers.storage import get_storage


class DocumentProvider:
	name = "abstract"

	def open(self, file_id: str) -> dict:
		raise NotImplementedError

	def save_new_version(self, file_id: str, content: bytes) -> str:
		raise NotImplementedError


class NullEditor(DocumentProvider):
	name = "null"

	def open(self, file_id):
		f = frappe.get_doc("File", file_id)
		f.check_permission("read")
		return {"mode": "download", "url": get_storage().get_url(file_id), "file_name": f.file_name}

	def save_new_version(self, file_id, content):
		"""Upload a new version next to the old one; the old file stays (archive, never overwrite)."""
		old = frappe.get_doc("File", file_id)
		old.check_permission("write")
		folder_path = _folder_path(old.folder)
		base, dot, ext = old.file_name.rpartition(".")
		stamp = frappe.utils.now_datetime().strftime("%Y%m%d-%H%M%S")
		new_name = f"{base or ext} (v{stamp}){dot}{ext if base else ''}"
		return get_storage().put(folder_path, new_name, content, project=old.cc_project,
			client_visible=bool(old.cc_client_visible))


def _folder_path(folder: str) -> str:
	parts = []
	while folder and folder != "Home":
		row = frappe.db.get_value("File", folder, ["file_name", "folder"], as_dict=True)
		if not row:
			break
		parts.append(row.file_name)
		folder = row.folder
	return "/".join(reversed(parts))


class OnlyOfficeEditor(DocumentProvider):
	"""The ONLYOFFICE Document Server (P1-17, D-073): an editor config; saves arrive through the signed callback."""

	name = "onlyoffice"

	def open(self, file_id):
		from construction_core.office.api import editor_config

		return {"mode": "editor", **editor_config(file_id)}

	def save_new_version(self, file_id, content):
		return NullEditor().save_new_version(file_id, content)


def get_document_provider() -> DocumentProvider:
	path = frappe.conf.get("cc_document_provider")
	if path:
		return frappe.get_attr(path)()
	return OnlyOfficeEditor() if frappe.conf.get("cc_office_jwt_secret") else NullEditor()  # D-082 fallback
