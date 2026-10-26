"""Frozen copies of what a client is shown (design §4.3, D-428).

The bytes live at ``<site>/private/cc_approvals/<aa>/<sha256>``, outside ``private/files``, so no File row and none of
Frappe's file routes can serve them; only ``approvals.file`` does, after the request's read rule.

- ``store`` writes a copy atomically (a temporary file, then a link to its name, a rename that never replaces) before
  the row that names it is inserted, and never rewrites one: every file here is named by the SHA-256 of its bytes on
  disk (sealed bytes when sealed, so deploy/restore.sh checks each file against its name), and storing the same bytes
  again only checks those there. A rolled-back request's copy is never removed; ``remove`` is retention's alone (P3-81).
- ``read`` gives a copy's bytes back only when the bytes on disk still hash to its name, checked before unsealing.
- ``original`` reads a project File's stored bytes with ``versions.read_bytes``, never ``get_content``.
- ``freeze`` stores a shown copy and returns its entry for ``log.open_request``: key, name, type, size, revision letter,
  the original's SHA-256 and the shown copy's (computed once here, never again: re-encoding is not byte-stable).

The hooks the later rows use: P3-77 cleans the bytes (``clean_image``) before ``freeze``; P3-78 encrypts signature
pictures through ``seal`` (on store) and ``unseal`` (on read); the file is named by the sealed bytes, so a caller that
binds the plain bytes (the signature picture's SHA-256, §4.1) keeps that hash itself.
"""

import contextlib
import hashlib
import json
import os
import re

import frappe
from frappe import _
from frappe.utils import get_site_path

from construction_core.files.versions import read_bytes

FOLDER = "cc_approvals"
SHA = re.compile(r"^[0-9a-f]{64}$")
KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TYPE = re.compile(r"^[a-z]+/[a-z0-9.+-]{1,100}$")
INLINE = frozenset({"image/png", "image/jpeg", "image/webp", "application/pdf"})  # every other type downloads
NAME_MAX = 140


def path_of(sha: str | None) -> str | None:
	if not isinstance(sha, str) or not SHA.match(sha):
		return None
	return get_site_path("private", FOLDER, sha[:2], sha)


def store(content: bytes, seal=None) -> str:
	"""The name of the bytes written (``seal(content)`` when sealed): their SHA-256, the file's name on disk."""
	if not isinstance(content, bytes) or not content:
		frappe.throw(_("A frozen copy needs its bytes"))
	data = seal(content) if seal else content
	if not isinstance(data, bytes) or not data:
		frappe.throw(_("A frozen copy needs its bytes"))
	sha = hashlib.sha256(data).hexdigest()
	path = path_of(sha)
	if os.path.exists(path):
		if read(sha) is None:
			frappe.throw(_("A frozen copy on disk does not match its name"))
		return sha
	os.makedirs(os.path.dirname(path), exist_ok=True)
	tmp = f"{path}.tmp-{frappe.generate_hash(length=10)}"
	try:
		with open(tmp, "xb") as fh:
			fh.write(data)
			fh.flush()
			os.fsync(fh.fileno())  # evidence: on disk before the row that names it
		os.link(tmp, path)  # atomic like a rename, but never over a copy a concurrent store put there first
	except FileExistsError:
		if read(sha) is None:
			frappe.throw(_("A frozen copy on disk does not match its name"))
	finally:
		if os.path.exists(tmp):
			os.remove(tmp)
	return sha


def read(sha: str | None, unseal=None) -> bytes | None:
	path = path_of(sha)
	if not path or not os.path.isfile(path):
		return None
	with open(path, "rb") as fh:
		content = fh.read()
	if hashlib.sha256(content).hexdigest() != sha:
		return None  # before unsealing: what is unsealed is what the name vouches for
	return unseal(content) if unseal else content


def remove(sha: str | None) -> None:
	"""A signature picture deleted at its request's retention end (§4.8; approvals.retention, after its commit only)."""
	path = path_of(sha)
	if path:
		with contextlib.suppress(FileNotFoundError):  # removed already: a job run again after a failed commit
			os.remove(path)


def original(file: str) -> bytes:
	return read_bytes(frappe.get_doc("File", file))


def freeze(content: bytes, *, key: str, name: str, ctype: str, original_sha256: str, rev: str = "") -> dict:
	"""Store a shown copy (already cleaned) and return its entry."""
	name = os.path.basename(str(name or "").replace("\\", "/")).strip()
	if (not isinstance(key, str) or not KEY.match(key) or not isinstance(ctype, str) or not TYPE.match(ctype)
			or not isinstance(original_sha256, str) or not SHA.match(original_sha256) or not name
			or len(name) > NAME_MAX or any(ord(c) < 32 for c in name) or not isinstance(rev, str) or len(rev) > 8):
		frappe.throw(_("This file cannot be frozen"))
	return {"key": key, "name": name, "type": ctype, "size": str(len(content)), "rev": rev,
		"original_sha256": original_sha256, "shown_sha256": store(content)}


def entry_of(request, key) -> dict | None:
	"""A request's frozen entry by key, or None."""
	if not isinstance(key, str) or not KEY.match(key):
		return None
	try:
		entries = json.loads(request.frozen_files or "{}")
	except ValueError:
		return None
	entry = entries.get(key) if isinstance(entries, dict) else None
	if not isinstance(entry, dict) or not SHA.match(str(entry.get("shown_sha256"))) \
			or not TYPE.match(str(entry.get("type"))):
		return None
	return entry
