"""The system description of the approvals ledger (design §4.9; P3-81): the procedure, the checks, the app versions and
the IRR Annex 2 reliability factors, for the firm's custodian or witness (Rules on Electronic Evidence, Rules 8 and 9).
``current`` builds it, ``text`` is its plain text for the evidence pack, and ``fingerprint`` hashes the versions part
only: the daily job (approvals.digest) writes a ``build`` event when it changes.
"""

import importlib
import json
import os
import subprocess

import frappe

from construction_core.approvals import canonical

APPS = ("frappe", "construction_core", "construction_shell")
CHECKS = ("the sequence numbers and every link and hash of each project's chain",
	"the canonical text against the stored columns, and each request's snapshot against its terms hash",
	"each request's state against its last event; the approvers and switches against the chain",
	"the chosen option against its event, and drift between each record and its approved terms",
	"the frozen copies and the evidence PDFs: the stored bytes against their SHA-256 names",
	"receipts (any answer with none sent after 24 hours), Email Account changes, and anchors",
	"the chain heads in the outside mails (receipts and daily digests) against the chain")
PROCEDURE = ("A client signs in to the portal, accepts the agreement, and approves or returns a record exactly as shown. "
	"The terms shown are frozen and hashed. The answer is one event in the project's chain: each event's hash is the "
	"SHA-256 of the previous hash and its own canonical text. The signer gets a receipt, other approvers get the chain "
	"position, and a daily digest of every chain head goes to the firm's evidence mailbox. A daily check recomputes the "
	"whole chain.")
FACTORS = ("The system is kept only by this software; no one can edit or delete a chain row through Desk, REST or the API.",
	"The author of an answer is the signed-in client; the account's credentials and every change to them are chain events.",
	"Each event is time-stamped by the server in UTC and chained, so a change to any earlier event breaks every later hash.",
	"Copies of the chain heads are held outside the server (receipts, approver mails, the daily digest), so a rewrite is visible.",
	"The terms shown, the files shown and the locked line are frozen when the request is sent, and the answer binds their hashes.",
	"The system is checked every day and on every restore drill, and a failed check is mailed and recorded.",
	"The evidence PDF is stored once, its hash is in the chain, and it is checked by its stored bytes.")


def _commit(app: str) -> str:
	path = frappe.get_app_path(app, "..")
	try:
		return subprocess.run(["git", "-C", path, "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True,
			timeout=5, check=True).stdout.strip()
	except Exception:
		return os.environ.get(f"{app.upper()}_COMMIT", "")  # an image without .git: the build may set it


def versions() -> dict:
	return {"apps": {app: {"version": importlib.import_module(app).__version__ if app in frappe.get_installed_apps() else "",
		"commit": _commit(app)} for app in APPS}, "canonical_version": canonical.VERSION,
		"genesis_label": canonical.GENESIS_LABEL}


def current() -> dict:
	return {"versions": versions(), "checks": list(CHECKS), "procedure": PROCEDURE, "reliability_factors": list(FACTORS)}


def text() -> str:
	d, v = current(), versions()
	apps = [f"  {app}: {a['version'] or 'not installed'}" + (f" (commit {a['commit']})" if a["commit"] else "")
		for app, a in v["apps"].items()]
	return "\n".join(["System description", "", "Versions", *apps, f"  canonical text version: {v['canonical_version']}",
		f"  genesis label: {v['genesis_label']}", "", "Procedure", d["procedure"], "", "Checks run every day",
		*(f"- {c}" for c in d["checks"]), "", "Reliability factors (IRR Annex 2)", *(f"- {f}" for f in d["reliability_factors"]),
		""])


def fingerprint() -> str:
	return canonical.sha256(json.dumps(versions(), sort_keys=True))
