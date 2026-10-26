"""The approvals ledger's one writer (design §4.1-§4.4, §7; D-428): Approval Request, Approval Event and Approval
Evidence Detail are written here and nowhere else. Nothing here is whitelisted: request(), decide() and the other
endpoints (P3-77, P3-78) call these.

- **Claims** (the D-387 pattern): each write sets a request-local claim naming the very document object and the
  operation, consumed once by its controller (``LedgerRow``). No payload reaches ``frappe.flags``, so every REST and Desk
  insert and save is refused, a System Manager's and Administrator's too; db_insert and db_update, which skip every
  hook, pass only inside that very write. Deletes, renames and discards are refused for everyone;
  an evidence detail row goes only through ``clear_detail``, under its own claim, and changes only through
  ``clear_location`` (both from P3-81's retention job).
- **Lock order** everywhere (D-459): the subject row when a path locks it (``_lock_subject``), then the project row, then
  the request row (SELECT ... FOR UPDATE, ``lock``): Frappe's own save of a subject locks it before its controller locks
  the project. A request's subject columns never change, so they are read before the lock. The chain's last event is read
  with a locking read, so the next sequence number and previous hash are the latest committed ones, never the
  transaction's snapshot. ``retry_once`` wraps an endpoint: a lost race (MariaDB 1020 or 1213) is tried once more on a
  fresh snapshot, then "Please try again".
- **One chain per project**: sequence numbers from 1; each event's hash is SHA-256(previous hash + "\\n" + its canonical
  text), the first one's previous hash canonical.genesis(site, project), with the site in that first text. Times are the
  server's, UTC with microseconds; each event carries the chain's ``high_water`` (the latest time so far), and one earlier
  than it is written and flagged ``out_of_order`` in its text, never refused.
- **Terms**: ``terms_of`` dispatches to the kind registered for the subject's doctype (P3-77 registers the four kinds).
  A kind's builder asks ``sha_of(file)`` for each file it shows: before the lock the bytes are hashed (``Hashes``),
  inside it only the file's identity is compared and the earlier hash given back. ``terms_agree`` is the four-hash check.
- **State**: a request's state is its last state event's (``STATE_AFTER``) and moves only as ``TRANSITIONS`` allow; the
  status column follows the chain, and the controller refuses any other value. Every other column of a request is in
  its drafted or requested event's text (``request_body``), so a recompute compares them.
"""

import json
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.model.document import Document
from frappe.utils import getdate

from construction_core.approvals import canonical, frozen
from construction_core.discuss.api import lost_race_once
from construction_core.permissions import anchor_project, in_setup

REQUEST, EVENT, DETAIL = "Approval Request", "Approval Event", "Approval Evidence Detail"
ROUTE_VERSION = "Approval Route Version"  # P3-82 (§14.2): append-only under the same claim
DOCTYPES = (REQUEST, EVENT, DETAIL, ROUTE_VERSION)
CLAIM = "cc_approvals_claim"
RETENTION = "cc_approvals_retention"
LOCATION = "cc_approvals_location"  # P3-81: clear_location's claim, the one save an evidence detail row takes
PARTIES = {"requester_party": ("staff", "partner"), "decider_party": ("client", "partner")}  # partners: P3-32
INTERNAL = "In internal review"  # P3-82 (§14.3): staff-only; a request leaves it Superseded (sent on) or Voided
# A request's state is its last state event's (§4.4); the other kinds leave it as it is.
STATE_AFTER = {"drafted": "Draft", "requested": "Open", "approved": "Approved", "returned": "Returned",
	"superseded": "Superseded", "voided": "Voided", "internal_review": INTERNAL}
# the events that freeze a request's terms_hash. ``requested`` is the only one a client ever reads (approvals.read)
TERMS_EVENTS = ("drafted", "requested", "internal_review")
# The states a request's state may move to (§4.4), from none yet (its first event); a final state takes no state event.
# Approved is superseded while its record is not final (§3.10, P3-77: approvals.subjects decides when). P3-82: a request
# in internal review never opens itself: its last step sends a new Open request in its place (approvals.routes).
TRANSITIONS = {None: {"Draft", "Open", INTERNAL}, "Draft": {"Open", "Voided"},
	"Open": {"Approved", "Returned", "Superseded", "Voided"}, "Approved": {"Superseded"},
	INTERNAL: {"Superseded", "Voided"}}
# P3-82 (§14.5): a request's frozen route, and each internal step (staff-only; "same person" in each body)
INTERNAL_EVENTS = ("route_frozen", "internal_approved", "internal_returned", "internal_acknowledged")
# P3-81 (§4.6, §4.8, §4.9): the daily digest's anchor, a failed verify, an evidence PDF's hash, a legal hold set or
# lifted, retention's clearing of an answer's detail and of its location, an erase request answered, and an app build
SYSTEM_EVENTS = ("anchor", "verify_failed", "build")  # written by the jobs: no approver-head mail follows them
EVIDENCE_EVENTS = (*SYSTEM_EVENTS, "evidence_pdf", "legal_hold", "retention_cleared", "location_cleared",
	"erase_request_received")
# P3-77's set-up (approvals.api): a project's switches, an approver's designation, the evidence mailbox; a final record
# edited by a System Manager (approvals.subjects, §3.10); P3-78: an approver's agreement (approvals.agreement) and an
# account's credential events (approvals.credentials, §4.5); each receipt sent or not (approvals.receipts, §3.6) and a
# dispute and its exit (approvals.dispute, §3.7): flags, never a state, so an Approved or Returned request keeps its state;
# a staff-recorded approval waiting for its confirmation (approvals.recorded, §3.9) and each reminder or Nudge mailed
# to an approver (approvals.api, §3.10), counted toward the client limit
EVENT_KINDS = {*STATE_AFTER, "opened", "settings", "designation", "evidence_mailbox", "changed_after_decision",
	"agreed", "credential", "receipt_sent", "receipt_failed", "disputed", "dispute_resolved", "recorded", "reminded",
	*INTERNAL_EVENTS, *EVIDENCE_EVENTS}
DETAIL_FIELDS = ("network_address", "ip_trust", "user_agent", "browser", "system", "wsgi_peer", "location")
DETAIL_MAX = 2000
FROZEN_KEYS = ("key", "name", "type", "size", "rev", "original_sha256", "shown_sha256")


@dataclass(frozen=True)
class Kind:
	"""A subject kind. ``terms(name, sha_of)`` builds what the client is shown, in canonical values; each file shown is
	a row of ``terms["files"]`` holding its ``key`` and ``sha256`` = sha_of(File name). ``places``: the amounts' places.
	``allowed(doc)``: whether a request may be open on the record now (§3.1), checked again inside the lock."""

	terms: Callable
	places: int = 2
	allowed: Callable | None = None


KINDS: dict[str, Kind] = {}  # subject doctype -> Kind; approvals.subjects registers the four (imported at the end)


def register(doctype: str, terms: Callable, places: int = 2, allowed: Callable | None = None) -> None:
	KINDS[doctype] = Kind(terms, places, allowed)


def terms_of(doctype: str, name: str, sha_of: Callable) -> dict:
	"""The one builder of a subject's terms, for the request, the answer, the staff gate and the daily check."""
	kind = KINDS.get(doctype)
	if not kind:
		frappe.throw(_("{0} records cannot be sent for approval").format(_(doctype)))
	terms = kind.terms(name, sha_of)
	if not isinstance(terms, dict):
		frappe.throw(_("{0} records cannot be sent for approval").format(_(doctype)))
	return terms


class TermsChanged(frappe.ValidationError):
	"""A file the terms show changed, or appeared, after its bytes were hashed: the check cannot vouch for it."""


class UnknownVersion(frappe.ValidationError):
	"""A snapshot frozen in a canonical version this server does not rebuild: never a silent disagreement."""


class Hashes:
	"""``sha_of`` for terms_of. Called before the lock, it hashes each file's stored bytes (versions.read_bytes) and keeps
	the file's identity with the hash; ``locked()`` is the sha_of used inside the lock, which compares the identity only
	(a locking read, so the latest committed row) and gives back the hash taken before (§3.5 step 7)."""

	def __init__(self):
		self.seen = {}

	def __call__(self, file: str) -> str:
		if file not in self.seen:
			identity = _identity(file)
			if not identity:
				frappe.throw(_("A file of this record is missing"))
			content = frozen.original(file)
			# a consistency check outside the lock, never evidence: the bytes read are the ones the row names
			if not identity[3] or get_content_hash(content) != identity[3]:
				raise TermsChanged(_("This record changed just now. Please try again."))
			self.seen[file] = (identity, canonical.sha256(content))
		return self.seen[file][1]

	def locked(self) -> Callable:
		def sha_of(file: str) -> str:
			if file not in self.seen or _identity(file, lock=True) != self.seen[file][0]:
				raise TermsChanged(_("This record changed just now. Please try again."))
			return self.seen[file][1]

		return sha_of


def _identity(file, lock: bool = False) -> tuple | None:
	rows = frappe.db.sql(f"""select name, file_url, file_size, content_hash from `tabFile` where name = %s
		{'lock in share mode' if lock else ''}""", (file,))
	return tuple(rows[0]) if rows else None


def prehash(request: str) -> Hashes:
	"""Before the lock: the bytes of the files the request's live terms show, hashed."""
	r = frappe.db.get_value(REQUEST, request, ["subject_doctype", "subject_name"], as_dict=True)
	hashes = Hashes()
	if r and r.subject_doctype in KINDS:
		try:
			terms_of(r.subject_doctype, r.subject_name, hashes)
		except frappe.DoesNotExistError:
			pass  # the subject is gone: terms_agree says so
	return hashes


# --- locks ------------------------------------------------------------------------------------------------------


def lock(project: str, request: str | None = None):
	"""The lock order everywhere (§4.4, D-459): after the subject row when a path locks it, the project row, then the
	request row, each SELECT ... FOR UPDATE, held until the transaction ends. Returns the request row as locked, or
	None."""
	if not isinstance(project, str) or not frappe.db.sql(
			"select name from `tabConstruction Project` where name = %s for update", (project,)):
		raise frappe.DoesNotExistError(_("Not found"))
	if request is None:
		return None
	rows = frappe.db.sql("select * from `tabApproval Request` where name = %s for update", (request,), as_dict=True)
	if not rows or rows[0].project != project:
		raise frappe.DoesNotExistError(_("Not found"))
	return rows[0]


def _lock_subject(doctype: str, name: str) -> None:
	"""Before the project and the request (D-459): the subject's row, so the terms read inside the lock are its latest
	committed ones (a row changed after this transaction's snapshot fails the read with 1020, and retry_once starts
	again)."""
	if doctype not in KINDS:  # registered doctypes only reach the query
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.db.sql(f"select name from `tab{doctype}` where name = %s for update", (name,))
	for df in frappe.get_meta(doctype).get_table_fields():  # P3-77 (C6): the child rows the terms read, locked with it
		frappe.db.sql(f"select name from `tab{df.options}` where parenttype = %s and parent = %s for update",
			(doctype, name))


def retry_once(fn: Callable):
	"""An endpoint's whole body, which wrote nothing before it: a lost race (MariaDB 1020 or 1213, QueryDeadlockError) is
	taken back and tried once more on a fresh snapshot (discuss.api.lost_race_once), then refused."""
	try:
		return lost_race_once(fn)
	except frappe.QueryDeadlockError:
		frappe.db.rollback()
		frappe.throw(_("Someone else was saving this approval at the same moment. Please try again."))


# --- writes -----------------------------------------------------------------------------------------------------


def open_request(project: str, subject_doctype: str, subject_name: str, *, frozen_entries=(), requester=None,
		requester_party="staff", decider_party="client", subject_title="", due_date=None, note="",
		retention_class="", retention_end=None, statement_versions=None, predecessor=None, draft=False,
		internal=False) -> str:
	"""Freeze a subject's terms into a new request and append its ``requested`` event (``drafted`` for a draft,
	``internal_review`` for one going through internal steps first, P3-82), under the lock. ``frozen_entries``: the shown
	copies (frozen.freeze), one per row of terms["files"], matched by key and the original's SHA-256. Returns the
	request's name."""
	first = "drafted" if draft else "internal_review" if internal else "requested"
	kind = KINDS.get(subject_doctype)
	if not kind:
		frappe.throw(_("{0} records cannot be sent for approval").format(_(subject_doctype)))
	if requester_party not in PARTIES["requester_party"] or decider_party not in PARTIES["decider_party"]:
		frappe.throw(_("Unknown party"))
	if anchor_project(subject_doctype, subject_name) != project:
		frappe.throw(_("This record is not in this project"))
	hashes = Hashes()
	terms_of(subject_doctype, subject_name, hashes)  # the file bytes, hashed before the lock
	shown = _frozen_map(frozen_entries)
	_lock_subject(subject_doctype, subject_name)
	if kind.allowed and not kind.allowed(frappe.get_doc(subject_doctype, subject_name)):  # the locked row (§6)
		frappe.throw(_("This record cannot be sent for approval in its current state"))
	lock(project)
	terms = terms_of(subject_doctype, subject_name, hashes.locked())
	files = terms.get("files") or []
	if not isinstance(files, list) or not all(isinstance(f, dict) for f in files) or \
			{f.get("key"): f.get("sha256") for f in files} != {k: e["original_sha256"] for k, e in shown.items()} \
			or len(files) != len(shown):
		frappe.throw(_("Each file the client is shown needs its frozen copy"))
	text = snapshot_text(project, subject_doctype, subject_name, terms, shown, kind.places)
	terms_hash = canonical.sha256(text)
	doc = _write(frappe.get_doc({"doctype": REQUEST, "project": project, "subject_doctype": subject_doctype,
		"subject_name": subject_name, "subject_title": str(subject_title or "")[:140],
		"requester": requester or frappe.session.user, "requester_party": requester_party,
		"decider_party": decider_party, "status": STATE_AFTER[first],
		"due_date": due_date, "note": note or "", "retention_class": retention_class or "",
		"retention_end": retention_end, "predecessor": predecessor or "",
		"statement_versions": json.dumps(statement_versions or {}, sort_keys=True, ensure_ascii=False),
		"snapshot": text, "terms_hash": terms_hash,
		"frozen_files": json.dumps(json.loads(text)["frozen"], sort_keys=True, ensure_ascii=False)}), "insert")
	append_event(project, first, request=doc.name, terms_hash=terms_hash, body=request_body(doc))
	return doc.name


def request_body(r) -> dict:
	"""A request's columns as its drafted or requested event's body holds them: all but the status and the successor,
	which move, and the project, terms_hash, snapshot and frozen_files, which the event and the terms_hash bind."""
	return {"subject_doctype": r.subject_doctype, "subject_name": r.subject_name, "subject_title": r.subject_title or "",
		"requester": r.requester, "requester_party": r.requester_party, "decider_party": r.decider_party,
		"due_date": _day(r.due_date), "note": r.note or "", "retention_class": r.retention_class or "",
		"retention_end": _day(r.retention_end), "predecessor": r.predecessor or "",
		"statement_versions": json.loads(r.statement_versions or "{}")}


def _day(value) -> str:
	return getdate(value).isoformat() if value else ""  # getdate(None) is today


def snapshot_text(project, doctype, name, terms, shown, places) -> str:
	"""What a request's terms_hash covers: its project, its subject, the subject's terms and the shown copies by key."""
	return canonical.text({"project": project, "subject": {"type": doctype, "name": name}, "terms": terms,
		"frozen": shown}, places)


def _frozen_map(entries) -> dict:
	shown = {}
	for e in entries or ():
		if not isinstance(e, dict) or set(e) != set(FROZEN_KEYS) or not all(isinstance(e[k], str) for k in FROZEN_KEYS):
			frappe.throw(_("This file cannot be frozen"))
		path = frozen.path_of(e["shown_sha256"])
		if (e["key"] in shown or not frozen.KEY.match(e["key"]) or not frozen.SHA.match(e["original_sha256"])
				or not frozen.TYPE.match(e["type"]) or not path or not os.path.isfile(path)):
			frappe.throw(_("This file cannot be frozen"))
		shown[e["key"]] = {k: e[k] for k in FROZEN_KEYS}
	return shown


def append_event(project: str, kind: str, *, request=None, terms_hash=None, body=None, places=None,
		detail=None) -> str:
	"""Append one event to the project's chain, under the lock (the project row, then the request row); returns its
	name. The actor is always the session user, never a caller's value (§6). ``detail``: an answer's personal values
	(DETAIL_FIELDS), kept in their own row; the event holds only a salted commitment to them (§4.1). A state event
	(STATE_AFTER) needs its request, moves only as TRANSITIONS allow from the chain's state, and moves the request's
	status with it; a terms event carries the locked request's own terms_hash."""
	if kind not in EVENT_KINDS:
		frappe.throw(_("Unknown approval event"))
	if kind in STATE_AFTER and not request:
		frappe.throw(_("This approval event needs its request"))
	row = lock(project, request)
	if kind in STATE_AFTER and STATE_AFTER[kind] not in TRANSITIONS.get(state_of(request), ()):
		frappe.throw(_("This approval request cannot move to {0} now").format(_(STATE_AFTER[kind])))
	if kind in TERMS_EVENTS and terms_hash != row.terms_hash:
		frappe.throw(_("This approval event does not carry its request's terms"))
	head = frappe.db.sql("""select seq, hash, high_water from `tabApproval Event` where project = %s
		order by seq desc limit 1 for update""", (project,), as_dict=True)
	head = head[0] if head else None
	at = _now()
	at_utc = at.replace(tzinfo=None)  # naive UTC, as the columns hold it
	late = bool(head and at_utc < head.high_water)
	high_water = max(head.high_water, at_utc) if head else at_utc
	prev = head.hash if head else canonical.genesis(frappe.local.site, project)
	seq = head.seq + 1 if head else 1
	data = {"project": project, "seq": seq, "kind": kind, "at": at, "time_zone": frappe.utils.get_system_timezone(),
		"actor": frappe.session.user, "out_of_order": "1" if late else "0", "body": body or {},
		"high_water": high_water.replace(tzinfo=timezone.utc)}
	if seq == 1:
		data["site"] = frappe.local.site  # append-only: the genesis is rebuilt from the chain alone, never added later
	if request:
		data["request"] = request
	if terms_hash:
		data["terms_hash"] = terms_hash
	values, salt = None, None
	if detail is not None:
		values, salt = _detail_values(detail), secrets.token_hex(16)  # 128 random bits
		data["detail_commitment"] = canonical.sha256(f"{salt}\n{canonical.text(values)}")
	text = canonical.text(data, places)
	doc = _write(frappe.get_doc({"doctype": EVENT, "project": project, "seq": seq, "kind": kind, "request": request,
		"actor": data["actor"], "at_utc": at_utc, "high_water": high_water, "out_of_order": int(late),
		"terms_hash": terms_hash, "prev_hash": prev, "hash": canonical.link(prev, text), "canonical": text}), "insert")
	if salt:
		_write(frappe.get_doc({"doctype": DETAIL, "event": doc.name, "project": project, "salt": salt, **values}),
			"insert")
	if request and kind in STATE_AFTER:
		r = frappe.get_doc(REQUEST, request)
		if r.status != STATE_AFTER[kind]:
			r.status = STATE_AFTER[kind]
			_write(r, "save")
	return doc.name


def _now() -> datetime:
	return datetime.now(timezone.utc)


def _detail_values(detail) -> dict:
	if (not isinstance(detail, dict) or not set(detail) <= set(DETAIL_FIELDS)
			or not all(isinstance(v, str) and len(v) <= DETAIL_MAX for v in detail.values())):
		frappe.throw(_("Unknown evidence detail"))
	return {f: detail.get(f, "") for f in DETAIL_FIELDS}


def state_of(request: str) -> str | None:
	"""A request's state: its last state event's (§4.4), what the staff gate and the portal take."""
	rows = frappe.db.sql("""select kind from `tabApproval Event` where request = %s and kind in %s
		order by seq desc limit 1""", (request, tuple(STATE_AFTER)))
	return STATE_AFTER[rows[0][0]] if rows else None


def terms_agree(request: str, hashes: Hashes) -> bool:
	"""The four-hash check (§3.5 step 7), inside the lock: SHA-256 of the stored snapshot, the request's terms_hash, the
	terms_hash of its requested event, and the live terms_of(subject) bound to the stored shown copies, all equal.
	``hashes`` is prehash(request), taken before the lock; TermsChanged (a file changed since) asks to try again. The live
	text is rebuilt with the snapshot's own places; a snapshot of another canonical version raises UnknownVersion."""
	s = frappe.db.get_value(REQUEST, request, ["project", "subject_doctype", "subject_name"], as_dict=True) \
		if isinstance(request, str) else None  # never changed, so read before the lock: the subject is locked first
	if not s:
		raise frappe.DoesNotExistError(_("Not found"))
	if s.subject_doctype not in KINDS:
		return False
	_lock_subject(s.subject_doctype, s.subject_name)
	r = lock(s.project, request)
	frozen_at = frappe.db.sql("select terms_hash from `tabApproval Event` where request = %s and kind in %s",
		(request, TERMS_EVENTS), pluck=True)
	try:
		snapshot = json.loads(r.snapshot or "")
		version, places = snapshot.get("canonical_version"), snapshot.get("places")
		places = None if places is None else int(places)
	except (ValueError, TypeError, AttributeError):
		return False  # a stored snapshot that is not a canonical text
	if version != canonical.VERSION:
		raise UnknownVersion(_("This request was frozen in canonical version {0}, which this server does not rebuild")
			.format(version))
	try:
		live = canonical.sha256(snapshot_text(r.project, r.subject_doctype, r.subject_name,
			terms_of(r.subject_doctype, r.subject_name, hashes.locked()), json.loads(r.frozen_files or ""), places))
	except (ValueError, TypeError, frappe.DoesNotExistError):
		return False  # a stored list that is not JSON, or a subject that is gone or no longer canonical
	return bool(frozen_at) and len({canonical.sha256(r.snapshot or ""), r.terms_hash, live, *frozen_at}) == 1


def clear_detail(name: str) -> None:
	"""The one way an evidence detail row goes (§4.8): at its request's retention end, from P3-81's job. Deleted
	permanently, so no Deleted Document keeps a copy; the event keeps its commitment."""
	frappe.flags[RETENTION] = frappe._dict(name=name, consumed=False)
	try:
		frappe.delete_doc(DETAIL, name, ignore_permissions=True, force=True, delete_permanently=True)
	finally:
		frappe.flags[RETENTION] = None


def clear_location(name: str) -> None:
	"""The one change an evidence detail row takes (§4.1, §4.8): its location emptied at project completion, from P3-81's
	job, which writes the ``location_cleared`` event. The event keeps its commitment to the value that was there."""
	doc = frappe.get_doc(DETAIL, name)
	if not doc.location:
		return
	doc.location = ""
	frappe.flags[LOCATION] = name
	try:
		_write(doc, "save")
	finally:
		frappe.flags[LOCATION] = None


def _write(doc, op: str):
	frappe.flags[CLAIM] = frappe._dict(op=op, doc=doc, consumed=False)
	try:
		# ignore_permissions: the ledger's own write (§4.4); the controller still checks the claim
		if op == "insert":
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)
	finally:
		frappe.flags[CLAIM] = None
	return doc


def _consume(doc, op: str) -> None:
	claim = frappe.flags.get(CLAIM)
	if not claim or claim.consumed or claim.op != op or claim.doc is not doc:
		refuse()
	claim.consumed = True


def _writing(doc, op: str) -> None:
	"""db_insert and db_update run raw SQL and no hook, and a template's or a script's live Document reaches them
	(bypass-2): only ``_write``'s own insert or save of this very document, once its controller consumed the claim."""
	claim = frappe.flags.get(CLAIM)
	if not (claim and claim.consumed and claim.op == op and claim.doc is doc):
		refuse()


def refuse():
	frappe.throw(_("Approval records are written by the server only, and never changed, renamed or deleted"),
		frappe.PermissionError)


class LedgerRow(Document):
	"""The no-bypass controller of the three ledger doctypes (§4.4): an insert or a save only under ``_write``'s claim for
	this very document, consumed once; a delete or a rename never, by anyone, System Manager and Administrator too."""

	def before_insert(self):
		_consume(self, "insert")
		self.check_insert()

	def before_validate(self):
		if not self.is_new():  # before_validate runs on every save, ignore_validate or not
			_consume(self, "save")
			self.check_save()

	def check_insert(self) -> None:
		"""What the row's own values must agree on."""

	def check_save(self) -> None:
		refuse()  # append-only

	def db_insert(self, *args, **kwargs):
		_writing(self, "insert")
		return super().db_insert(*args, **kwargs)

	def db_update(self):
		_writing(self, "save")
		return super().db_update()

	def before_change(self):
		_writing(self, "save")  # db_set runs it before its set_value; the ledger never uses db_set (bypass-8)

	def add_tag(self, tag):
		refuse()  # DocTags writes _user_tags before its Tag Link, and a caller that swallows the throw keeps it

	def remove_tag(self, tag):
		refuse()

	def update_modified(self):
		refuse()  # a set_value with no hook, which an expression's or a template's live Document reaches (round 5)

	def queue_action(self, action, **kwargs):
		refuse()  # its job would run the action later, outside any safe-render flag (round 5)

	def before_discard(self):
		refuse()  # Document.discard is whitelisted, checks write only, and db_sets docstatus 2 with no claim

	def on_trash(self):
		refuse()

	def after_delete(self):
		refuse()  # reached when delete_doc skipped on_trash (ignore_on_trash)

	def before_rename(self, old, new, merge=False):
		refuse()

	def after_rename(self, old, new, merge=False):
		refuse()  # reached when rename_doc skipped before_rename (validate=False)


# --- hooks on other doctypes ------------------------------------------------------------------------------------


def refuse_project_delete(doc, method=None):
	"""Construction Project on_trash and after_delete (D-092 and DR-7, amended by D-427): a project with approval records
	is archived, never deleted, by anyone. A locking read also sees a request committed after this delete began."""
	if frappe.db.sql("select name from `tabApproval Event` where project = %s limit 1 lock in share mode", (doc.name,)) \
			or frappe.db.sql("select name from `tabApproval Request` where project = %s limit 1 lock in share mode",
				(doc.name,)):
		frappe.throw(_("This project has approval records, so it cannot be deleted. Archive it instead."),
			frappe.PermissionError)


def refuse_named_rename(doc, method=None, old=None, new=None, merge=False):
	"""before_rename and after_rename of every scoped doctype (D-427): a record named in an approval request keeps its
	name while the request exists (requests are never deleted), and a project with approval records keeps its own. The
	record's own row is locked first, then the ledger is read with locking reads, so a request committed meanwhile is
	seen. after_rename is reached when rename_doc skipped before_rename (validate=False); its throw rolls back the Link
	rewrites."""
	old = old or doc.name
	frappe.db.sql(f"select name from `tab{doc.doctype}` where name = %s for update", (doc.name,))
	named = frappe.db.sql("""select name from `tabApproval Request` where subject_doctype = %s and subject_name = %s
		limit 1 lock in share mode""", (doc.doctype, old))
	if not named and doc.doctype == "Construction Project":
		# after_rename: the ledger's project Links already hold the new name (update_link_field_values)
		named = frappe.db.sql("select name from `tabApproval Event` where project in %s limit 1 lock in share mode",
			(tuple({old, doc.name}),))
	if named:
		frappe.throw(_("This record is named in an approval request, so it cannot be renamed."), frappe.PermissionError)


def stored_doctype(name):
	"""A doctype name as the database stores it, or the name itself when no DocType matches (round 5, D4). MariaDB
	compares names folding case, trailing spaces and accents (utf8mb4_unicode_ci), so "approval request " names Approval
	Request in a Link and in a set_value; Frappe's link check stores the matched name only after the before_validate and
	validate hooks."""
	return (frappe.db.get_value("DocType", name, "name") if name and isinstance(name, str) else None) or name


def not_ledger(doctype):
	"""An override's doctype argument as stored, refused when it names a ledger doctype (round 5, D2-D4)."""
	doctype = stored_doctype(doctype)
	if doctype in DOCTYPES:
		refuse()
	return doctype


REFERENCE_FIELD = {"ToDo": "reference_type", "Tag Link": "document_type"}  # the others: reference_doctype


def refuse_ledger_reference(doc, method=None):
	"""Comment, ToDo, Communication, Communication Link and Tag Link before_validate, on insert and on every save
	(P3-76), and before_cancel and before_update_after_submit, which a docstatus 2 or 1 save runs instead (round 5, D5):
	none names a ledger row, so a client-readable request's _comments, _assign, _user_tags and modified stay as
	the ledger wrote them (Frappe copies a comment's text, an assignee and a tag into them; a Communication moves
	modified). A Comment's link and a Communication's timeline links count too, and a Communication Link saved on its own
	(frappe.client.save). Communication validate too: an email's controller adds timeline links after before_validate
	(its recipients' +doctype forms, its contacts' Dynamic Links). Each name as the database matches it (D4)."""
	named = {doc.get(REFERENCE_FIELD.get(doc.doctype, "reference_doctype")), doc.get("link_doctype"),
		*(row.link_doctype for df in doc.meta.get_table_fields() if df.options in ("Communication Link", "Dynamic Link")
			for row in doc.get(df.fieldname) or ())}
	if {stored_doctype(n) for n in named} & set(DOCTYPES):
		frappe.throw(_("Approval records take no comments, assignments or tags"), frappe.PermissionError)


def refuse_ledger_link(doc, method=None):
	"""Contact, Address, Event, Web Form Request and Dynamic Link before_validate, before_cancel and
	before_update_after_submit (round 5, D6): outside setup, no Dynamic Link names a ledger row. A Communication adds its
	contacts' links to its timeline, so a Contact linked to a request would make every email to or from it fail."""
	if not in_setup():
		refuse_ledger_reference(doc)


def refuse_ledger_customization(doc, method=None, *args):
	"""DocType before_validate and before_rename; Custom Field, Property Setter, Custom DocPerm, DocPerm, DocField,
	DocType Action, DocType Link and DocType State before_validate (bypass-1): a ledger doctype is its JSON, changed by
	migrate only. A System Manager could otherwise make one custom (Frappe then loads a plain Document, and LedgerRow's
	refusals are gone), a child table, the rows of another record's Table field, or give a role permissions on it, also by
	saving one of its DocPerm or DocField rows on its own (frappe.client.save; a DocType's own save writes its rows with
	no hook). Customize Form saves a custom DocType Action, Link or State row with its own save (round 4). Install,
	migrate, patches and uninstall write these, under their flags. Frappe never calls on_trash for a DocType; it refuses
	deleting a standard one while developer mode is off."""
	if in_setup():
		return
	named = {"DocType": (doc.name,), "Custom DocPerm": (doc.get("parent"),), "DocPerm": (doc.get("parent"),),
		"DocField": (doc.get("parent"), doc.get("options")), "Custom Field": (doc.get("dt"), doc.get("options")),
		"Property Setter": (doc.get("doc_type"), doc.get("value") if doc.get("property") == "options" else None),
		"DocType Action": (doc.get("parent"),), "DocType Link": (doc.get("parent"),),
		"DocType State": (doc.get("parent"),),
	}[doc.doctype]
	if {stored_doctype(n) for n in named} & set(DOCTYPES):  # as the database matches names (D4)
		frappe.throw(_("Approval records are defined by the app, so their doctypes cannot be customized"),
			frappe.PermissionError)


AUTOMATION_FIELD = {"Webhook": "webhook_doctype", "Auto Repeat": "reference_doctype"}  # the others: document_type


def refuse_ledger_automation(doc, method=None):
	"""Assignment Rule, Notification, Automation Flow, Webhook, Workflow, Auto Repeat, Milestone Tracker and Document
	Naming Rule before_validate (round 4): none targets a ledger doctype. A "*" on_update/on_cancel/on_change hook
	(assignment_rule.apply, milestone_tracker.evaluate_milestone) would insert a ToDo or Milestone the ledger write then
	refuses, breaking the write; a Notification would fail silently and log an Error Log per write; an Automation Flow's
	condition, a Webhook's condition/payload, or a Workflow's state field runs against the live row and its evidence; a
	Document Naming Rule would seize the ledger's own naming on insert. Auto Repeat can never enable (its
	allow_auto_repeat is a refused Property Setter); refused cleanly here rather than on a missing-column error. Refused
	at configuration, so a rule that already exists before this hook (there is none) is not caught here. Install and
	migrate write none of these."""
	if in_setup():
		return
	if stored_doctype(doc.get(AUTOMATION_FIELD.get(doc.doctype, "document_type"))) in DOCTYPES:  # (D4)
		frappe.throw(_("Approval records take no automation rules"), frappe.PermissionError)


# The four subject kinds register themselves (§3.1); last, so that module finds this one whole.
from construction_core.approvals import subjects  # noqa: E402, F401
