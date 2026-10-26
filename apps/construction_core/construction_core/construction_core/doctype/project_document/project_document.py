# Copyright (c) 2026, Construction Workspace and contributors
"""Project Document: ISO 19650 document control (ARCHITECTURE §6.8; DESIGN-PHASE-LIFECYCLE spec §3.1).

States: WIP -> Lead Review -> Shared -> Coordination Review -> (Client Review) -> Published -> Archived.
A new revision of the same document number, once Published, archives the previous Published revision: the stored
state is ``Archived`` and the event is ``document.superseded`` (D-069).
A Published, Archived or Cancelled document is final (only supersession archives it), the publication hash is set by
the server only, and only a WIP document can be deleted.
"""

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document

from construction_core.core.events import emit
from construction_core.files.versions import read_bytes
from construction_core.permissions import _bypass

TRANSITIONS = {
	"WIP": {"Lead Review", "Cancelled"},
	"Lead Review": {"WIP", "Shared"},
	"Shared": {"Coordination Review", "WIP"},
	"Coordination Review": {"WIP", "Client Review", "Published"},
	"Client Review": {"WIP", "Published"},
	"Published": {"Archived"},
	"Archived": set(),
	"Cancelled": set(),
}
FINAL = {"Published", "Archived", "Cancelled"}


class ProjectDocument(Document):
	def before_insert(self):
		if not self.author:
			self.author = frappe.session.user
		if self.status not in ("WIP", None, ""):
			frappe.throw(_("A new document starts in WIP"))

	def validate(self):
		before = self.get_doc_before_save()
		self.approved_revision_hash = before.approved_revision_hash if before else None
		if before and before.status in FINAL and not _bypass(frappe.session.user):
			if not (self.flags.superseding and before.status == "Published" and self.status == "Archived"):
				frappe.throw(_("A {0} document is final: issue a new revision").format(_(before.status)),
					title=_("Document is final"))
		if before and before.status != self.status:
			self._check_transition(before.status, self.status)
		if self.document_file:
			if frappe.db.get_value("File", self.document_file, "cc_project") != self.project:
				frappe.throw(_("The document file must belong to the same project"))
			if frappe.db.get_value("File", self.document_file, "cc_version_of"):  # P3-43 audit note 2
				frappe.throw(_("Choose the file itself: an earlier version is kept in its history"))

	def _check_transition(self, old, new):
		if new not in TRANSITIONS.get(old, set()):
			frappe.throw(_("A document cannot move from {0} to {1}").format(_(old), _(new)), title=_("Invalid state"))
		if old == "Coordination Review" and new == "Published" and self.client_approval_required:
			frappe.throw(_("This document needs client approval: move it to Client Review first"))
		if new == "Archived" and not self.flags.superseding:
			frappe.throw(_("A document is archived only when a newer revision is published"))

	def on_trash(self):
		if self.status != "WIP" and not _bypass(frappe.session.user):
			frappe.throw(_("Only a WIP document can be deleted"), frappe.PermissionError)

	def on_update(self):
		from construction_core.approvals import subjects  # here: approvals loads the ledger

		subjects.check(self)  # P3-77: the client's approval, on the saved terms (§3.10, §3.11)
		if not self.has_value_changed("status"):
			return
		if self.status == "Published":
			self._on_published(subjects.approved_file_sha(self.name))
		emit("document.status_changed", self)

	def _on_published(self, approved: str | None):
		"""P3-77 (§3.11): the hash of the stored bytes (get_content decodes a text file, a DXF too), or the original the
		client's approval froze."""
		if self.document_file:
			self.db_set("approved_revision_hash", approved or hashlib.sha256(read_bytes(frappe.get_doc("File",
				self.document_file))).hexdigest())
			if self.client_visible:
				frappe.db.set_value("File", self.document_file, "cc_client_visible", 1)
		for old in frappe.get_all(
			"Project Document",
			filters={"project": self.project, "document_number": self.document_number, "status": "Published",
				"name": ["!=", self.name]},
			pluck="name",
		):
			prev = frappe.get_doc("Project Document", old)
			prev.status = "Archived"
			prev.flags.superseding = True
			# ignore_permissions: archiving the old revision is a consequence of publishing this one.
			prev.save(ignore_permissions=True)
			_withdraw_from_clients(prev.document_file, keep=self.document_file)
			emit("document.superseded", prev)
			if not self.supersedes:
				self.db_set("supersedes", old)
		emit("document.published", self)


def _withdraw_from_clients(file: str | None, keep: str | None):
	"""A superseded drawing is no longer shown to clients (P1-11 exit audit), unless a Published client-visible
	document still uses the same file."""
	if not file or file == keep:
		return
	if frappe.db.exists("Project Document", {"document_file": file, "status": "Published", "client_visible": 1}):
		return
	frappe.db.set_value("File", file, "cc_client_visible", 0, update_modified=False)

