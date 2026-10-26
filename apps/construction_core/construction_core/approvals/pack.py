"""The evidence pack (approvals design §4.6, §4.8 end of service): one zip per project that a court, the client or the
firm's lawyer checks without this server, with tools/verify_chain.py (standard library only).

Inside the zip: ``events.jsonl`` (each event's name, seq, prev_hash, hash and canonical text, anchors included: they are
events), ``requests/<name>.json`` (the snapshot and its terms_hash), ``frozen/<sha256>`` (each frozen copy's bytes as
stored, signature pictures sealed, evidence PDFs too), ``description.txt`` (approvals.describe), ``verify_chain.py``,
``head.json`` and, only when asked, ``detail.jsonl`` (the personal detail rows with their salts, so the commitments
check). Packs go to ``<site>/private/files/evidence-packs``, never as a File row; System Manager only.
"""

import json
import os
import re
import zipfile
from datetime import datetime, timezone

import frappe
from frappe.utils import get_files_path

from construction_core.approvals import frozen, log, verify

TOOL = os.path.join(os.path.dirname(__file__), "tools", "verify_chain.py")
FOLDER = "evidence-packs"


def export(project: str, dest: str | None = None, include_detail: bool = False) -> str:
	"""Write the project's evidence pack into the folder ``dest`` (default: the site's) and return its path."""
	frappe.only_for("System Manager")
	events = frappe.get_all(log.EVENT, filters={"project": project}, fields=["name", "seq", "prev_hash", "hash",
		"canonical", "kind"], order_by="seq asc")
	if not events:
		raise frappe.DoesNotExistError(f"{project} has no approval records")
	dest = dest or get_files_path(FOLDER, is_private=True)
	os.makedirs(dest, exist_ok=True)
	stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
	path = os.path.join(dest, f"{re.sub(r'[^A-Za-z0-9_.-]', '_', project)}-{stamp}.zip")
	shas = set()
	with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED) as z:
		z.writestr("events.jsonl", "".join(json.dumps({k: e[k] for k in ("name", "seq", "prev_hash", "hash",
			"canonical")}, ensure_ascii=False) + "\n" for e in events))
		for e in events:
			try:
				body = json.loads(e.canonical).get("body")
			except (ValueError, AttributeError):
				continue  # verify names it; the pack carries the text as stored
			if isinstance(body, dict):
				shas.update(verify.files_of(e.kind, body))
		for r in frappe.get_all(log.REQUEST, filters={"project": project}, fields=["name", "terms_hash", "snapshot",
				"frozen_files"]):
			z.writestr(f"requests/{r.name}.json", json.dumps({"name": r.name, "terms_hash": r.terms_hash,
				"snapshot": r.snapshot}, ensure_ascii=False))
			try:
				shas.update(x["shown_sha256"] for x in json.loads(r.frozen_files or "{}").values())
			except (ValueError, AttributeError, KeyError, TypeError):
				pass
		for sha in sorted(shas):
			content = frozen.read(sha)
			if content is not None:  # a missing one (retention cleared, or lost) is what verify_chain then shows
				z.writestr(f"frozen/{sha}", content)
		if include_detail:
			names = {e.name for e in events}
			rows = frappe.get_all(log.DETAIL, filters={"project": project}, fields=["name", "event", "salt",
				*log.DETAIL_FIELDS])
			z.writestr("detail.jsonl", "".join(json.dumps({k: v or "" for k, v in d.items()}, ensure_ascii=False) + "\n"
				for d in rows if d.event in names))
		z.writestr("description.txt", _description())
		z.write(TOOL, "verify_chain.py")
		z.writestr("head.json", json.dumps({"project": project, "seq": events[-1].seq, "hash": events[-1].hash}))
	return path


def _description() -> str:
	try:
		from construction_core.approvals import describe

		return describe.text()
	except (ImportError, AttributeError):
		return "not available"


def end_of_service(dest: str) -> list[str]:
	"""A hosted firm leaving (§4.8): every project's pack with its personal detail, into ``dest``. Nothing is deleted:
	deletion is the operator's step, logged outside the chain."""
	frappe.only_for("System Manager")
	return [export(p, dest, include_detail=True)
		for p in frappe.get_all(log.EVENT, pluck="project", distinct=True, order_by="project")]
