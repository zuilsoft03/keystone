"""File extension (v16 ``extend_doctype_class``): downloads must pass the project check too.

``File.is_downloadable`` calls the File module's own ``has_permission`` directly, so app ``has_permission``
hooks never run on a download (P1-02 audit finding 3). This mixin adds the project-scoped check.

P3-07:
- Every file anyone but the team stores is scanned before Frappe writes it (D-159, D-183): a client's profile photo
  or private file of their own; ``portal_api.send_file`` scans the files clients send before it stores them.
- Two of Frappe's File calls skip our hooks and are closed. ``zip_files`` zips any file Frappe's own rule lets the
  caller read, our project check never asked. ``optimize_file`` writes the optimized image to
  ``/files/<file_name>`` before any check runs; a File's name need not be its own address (a client's file is stored
  under a name of its own), so it could write over another file.

P3-46 (D-308…D-310): a row on a project file's address is a reference to that file and opens only as it does
(``permissions.can_access``). So the rows that are not references keep addresses of their own (``save_file``), no
change gives a row another row's bytes (``validate``), and references outlive their file only as internal files of
its project (``on_trash``). A change of privacy moves the rows on its address only (``handle_is_private_changed``).
"""

import shutil
from pathlib import Path

import frappe
from frappe import _
from frappe.core.doctype.file.file import File
from frappe.core.doctype.file.utils import decode_file_content, get_safe_file_name
from frappe.utils import cint

from construction_core.permissions import _bypass, can_access, is_client


def _is_team(user: str) -> bool:
	return user == "Administrator" or frappe.get_cached_value("User", user, "user_type") == "System User"


class ProjectScopedFile:
	def before_insert(self):
		# File.before_insert writes the content to the public or private folder from is_private, before any
		# doc_event runs, so a project file is made private here first (P1-02 audit finding 7).
		if self.get("cc_project"):
			self.is_private = 1
		if not self.is_folder:
			self._check_type_size()
		if not self.is_folder and self.get("content") and not _is_team(frappe.session.user) and not self._generated():
			from construction_core.client_files import check_burst, scan

			check_burst(frappe.session.user)  # the same budget as send_file: every scan costs the scanner's time
			content = decode_file_content(self.content) if self.decode else self.content  # leaves the doc as it is
			scan(content.encode() if isinstance(content, str) else content, sent=False)
		super().before_insert()

	def _check_type_size(self):
		"""D-417 (P3-75): the site takes uploads up to 250 MB for model files (Revit, IFC, SketchUp); every other type
		stays at 100 MB, for the team and clients alike (D-182)."""
		from frappe.utils.file_manager import MaxFileSizeReachedError

		from construction_core.client_files import OTHER_MAX, check_signature, size_text, type_limit

		content = self.get("content")
		if content and self.decode:
			content = decode_file_content(content)
		size = len(content) if content else cint(self.file_size)
		ext = (self.file_name or "").rpartition(".")[2].lower()
		limit = type_limit(ext)
		if size > limit:
			frappe.throw(_("The file is larger than {0}").format(size_text(limit)), MaxFileSizeReachedError)
		if size > OTHER_MAX:  # only a model file may be this large: its bytes must start as one does
			head = content[:4096] if content else self._head()
			check_signature(ext, head.encode() if isinstance(head, str) else head)

	def _head(self) -> bytes:
		try:
			with open(self.get_full_path(), "rb") as fh:
				return fh.read(4096)
		except (OSError, frappe.ValidationError):
			frappe.clear_last_message()
			return b""

	def _generated(self) -> bool:
		"""A file the server makes for a client in a job, not bytes the client sent: Frappe's personal data export
		(P3-07 review, C6). Kept narrow: any other job that stores a client's bytes is still scanned."""
		return self.get("attached_to_doctype") == "Personal Data Download Request" and getattr(frappe.local, "job", None) is not None

	def save_file(self, content=None, decode=False, ignore_existing_file_check=False, overwrite=False):
		# A new upload with no project is stored as its own, never on the address of identical bytes Frappe already
		# keeps: that address may be a project file's, and a row on it opens only as that file does. A row inserted
		# with an address (a Library attach) is a reference and keeps it. Frappe sets flags.in_insert only after
		# before_insert, where this runs, and names a new File after it.
		if (self.is_new() or not self.name) and not self.file_url:
			self.flags.cc_upload = True  # bytes the caller sent, not an address it named (permissions.guard_shared_address)
			if not self.get("cc_project"):
				ignore_existing_file_check = True
				self.flags.ignore_duplicate_entry_error = True  # nor the address of the same bytes on the same record
		return super().save_file(content=content, decode=decode, ignore_existing_file_check=ignore_existing_file_check,
			overwrite=overwrite)

	def validate(self):
		# Before File.validate, which acts on is_private at once (handle_is_private_changed).
		before = None if self.is_new() or self.flags.in_insert or self.is_folder else self.get_doc_before_save()
		if before:
			self._refuse_public_project_bytes(before)
			self._refuse_other_bytes(before)
			if (before.file_name or "").rpartition(".")[2].lower() != (self.file_name or "").rpartition(".")[2].lower():
				self._check_type_size()  # P3-75: a renamed file keeps its type's size rule (D-417)
		super().validate()

	def _refuse_public_project_bytes(self, before):
		"""Making a private row public moves its stored file to /files/ with every row on its address
		(``handle_is_private_changed``), a project's own rows too, past force_private: refused for everyone while a
		project's file shares the address."""
		url = before.file_url or self.file_url
		if (cint(before.is_private) and not cint(self.is_private) and url and frappe.db.exists("File",
				{"file_url": url, "name": ["!=", self.name], "cc_project": ["is", "set"]})):
			frappe.throw(_("A project's files stay private"), frappe.PermissionError)

	def handle_is_private_changed(self):
		"""Frappe's move between the private and public folders, but the rows that follow are those on this file's
		old address, not every row with the same content hash (``update_existing_file_docs``): a row elsewhere with
		the same bytes has a stored file of its own (P3-47, D-313)."""
		if self.is_remote_file:
			return
		old_url = self.file_url
		file_name = old_url.split("/")[-1]
		private, public = (Path(frappe.get_site_path(folder, "files", file_name)) for folder in ("private", "public"))
		source, target, prefix = (public, private, "/private/files/") if cint(self.is_private) else (private, public, "/files/")
		new_url = f"{prefix}{file_name}"
		if new_url == old_url:
			return
		if not source.exists():
			frappe.throw(_("Cannot find file {} on disk").format(source), exc=FileNotFoundError)
		if target.exists():
			frappe.throw(_("A file with same name {} already exists").format(target), exc=FileExistsError)
		shutil.move(source, target)
		self.flags.original_path = {"old": source, "new": target}
		frappe.db.after_rollback.add(self.on_rollback)
		self.file_url = new_url
		table = frappe.qb.DocType("File")
		(frappe.qb.update(table).set(table.file_url, new_url).set(table.is_private, cint(self.is_private))
			.where(table.file_url == old_url).where(table.name != self.name)).run()
		# As Frappe's: the record the file is attached to follows it (a profile photo's user_image).
		if not (self.attached_to_doctype and self.attached_to_name and self.fetch_attached_to_field(old_url)):
			return
		if frappe.get_meta(self.attached_to_doctype).issingle:
			frappe.db.set_single_value(self.attached_to_doctype, self.attached_to_field, new_url)
		else:
			frappe.db.set_value(self.attached_to_doctype, self.attached_to_name, self.attached_to_field, new_url)

	def _refuse_other_bytes(self, before):
		"""A row pointed at another row's stored file gives its bytes under its own rules (a client-visible row on an
		internal file's address): refused for all but System Managers."""
		if ((self.file_url or "") != (before.file_url or "") and not _bypass(frappe.session.user)
				and frappe.db.exists("File", {"file_url": self.file_url, "name": ["!=", self.name]})):
			frappe.throw(_("This file cannot be saved here"), frappe.PermissionError)

	def on_trash(self):
		# P3-68 follow-up (retention): a file the chat made (an upload or a checked copy, sent or removed) is a project
		# record kept for the project's life plus 15 years. Removal only bins it; a real delete, by any route (REST,
		# Desk, delete_items, remove_attach, a server delete under someone's session), is a System Manager's alone.
		from construction_core.discuss import media

		if not _bypass(frappe.session.user) and media.chat_made(self.name):
			frappe.throw(_("A file sent in a conversation is kept as a project record."), frappe.PermissionError)
		super().on_trash()
		# The rows with no project on this file's address were references to it. When no other project file keeps the
		# address, they become internal files of this file's project, so deleting the file releases its bytes to nobody.
		if self.is_folder or not self.get("cc_project") or not self.file_url:
			return
		if frappe.db.exists("File", {"file_url": self.file_url, "name": ["!=", self.name], "cc_project": ["is", "set"]}):
			return
		frappe.db.set_value("File", {"file_url": self.file_url, "name": ["!=", self.name], "cc_project": ["is", "not set"]},
			{"cc_project": self.cc_project, "cc_client_visible": 0}, update_modified=False)

	def is_downloadable(self):
		return super().is_downloadable() and can_access(self, "read")

	@frappe.whitelist()
	def optimize_file(self):
		"""Only the team, only a file outside projects that owns its address under its own name (P3-07)."""
		refuse = _("This image cannot be optimized in place")
		stored = frappe.db.get_value("File", self.name, ["file_name", "file_url", "is_private", "cc_project"],
			as_dict=True) if self.name else None
		if not stored or not _is_team(frappe.session.user) or is_client(frappe.session.user) or stored.cc_project:
			frappe.throw(refuse, frappe.PermissionError)
		target = ("/private/files/" if stored.is_private else "/files/") + get_safe_file_name(stored.file_name)
		if (self.file_name != stored.file_name or self.file_url != stored.file_url or target != stored.file_url
				or frappe.db.count("File", {"file_url": stored.file_url}) != 1):
			frappe.throw(refuse, frappe.PermissionError)
		self.check_permission("write")
		return super().optimize_file()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def upload_file(chunk_index=None, total_chunk_count=None, chunk_byte_offset=None, method=None):
	"""Frappe's upload_file, routed here (hooks.py). Anyone not on the team uploads a file in one piece and to no other
	method: Frappe writes each chunk of a chunked upload to disk before any File exists, so no hook (and no scan,
	D-183) sees it, and a public chunk is served as it is (P3-07 review, C2). Frappe's handler then checks the rest."""
	from frappe.handler import upload_file as frappe_upload_file

	pieces = (chunk_index, total_chunk_count, chunk_byte_offset, method)
	if not _is_team(frappe.session.user) and any(p not in (None, "") for p in pieces):
		frappe.throw(_("Send the file in one piece."), frappe.PermissionError)
	return frappe_upload_file()


@frappe.whitelist()
def zip_files(files: str):
	"""Frappe's ``zip_files`` for the team only, and only with files the caller may download (P3-07, D-168's rule)."""
	from construction_core.overrides.desk import _team_only

	_team_only()
	names = frappe.parse_json(files)
	if not isinstance(names, list) or not names or len(names) > 500 or not all(isinstance(n, str) for n in names):
		frappe.throw(_("Choose the files to download"))
	docs = []
	for name in dict.fromkeys(names):
		if not frappe.db.exists("File", name):
			continue
		doc = frappe.get_doc("File", name)
		if not doc.is_folder and frappe.has_permission("File", "read", doc=doc) and doc.is_downloadable():
			docs.append(doc)
	frappe.response["filename"] = "files.zip"
	frappe.response["filecontent"] = File.zip_files(docs)
	frappe.response["type"] = "download"
