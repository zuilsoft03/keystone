"""The record resolver (design §3.5, §13.3; P3-66): (doctype, name, viewer) -> a card, or nothing.

Chat uses it first (the refs part's cards); the bell and search can move to it later. Rule 2: a message stores
(doctype, name) only, and the card is drawn when the message is read, with the viewer's own permissions. A record the
viewer cannot read, one that was deleted and one that never existed give the same answer: no card. Nothing of it is
copied into the message.

**RECORD_TYPES** is what chat may tag, one line per type: the card's ``type`` (its words' key), the title and state
fields, whether Simple mode offers it (rule 13: files and Canvas boards only) and the audiences whose rooms may tag
it. Partners join after go-live (D-444): P3-32 adds "Partner" to the audiences of File, RFI and Submittal, and a
company rule to ``audience_reads`` (files, RFIs and Submittals of their company only).

**Cost** (``cards``): one query for any number of cards and any mix of types. Each record type is read with its list
predicate as the viewer (the role's read and permissions.project_scoped: membership, the client rules, the switches),
and the selects and the page's File rows go into one ``UNION ALL``. Files cannot be listed as the
viewer (Frappe's File list rule shows a non-System user only their own files), so their rows are a plain read in the
same statement and the download rule is checked in memory (attachments.readable_files, which a test holds equal to
``has_permission``). Every answer goes into ``ctx.memo``, so respond()'s ``_ref`` check asks nothing more.

**Simple mode** is a view, never a lock (D-154): a card carries ``simple`` (whether Simple mode draws it) and the record
``number`` apart from its title, so a Simple screen shows a Question, an Item for review or a Change as the neutral card
and no record numbers (D-152). The core never reads the shell's mode setting.
"""

from dataclasses import dataclass

import frappe

from construction_core.permissions import CLIENT_SECTION, client_may_see, client_section_open

INTERNAL, CLIENT = "Internal", "Client"
CARD = "cc_card"  # ctx.memo: a card already resolved for this page and viewer (cards)


@dataclass(frozen=True)
class RecordType:
	doctype: str
	key: str  # the card's type and its words' key (chat.refs.<key>)
	title: str  # the field a card shows as its title
	state: str | None  # the field a card shows as its state; None: no state
	simple: bool  # offered by the # picker and drawn in Simple mode (rule 13)
	audiences: frozenset  # the rooms that may tag it
	number: bool = True  # the name is a record number (a File's is an id, never shown)
	reference: str | None = None  # the field with the number people know, when the name is a hash (an approval's record)


BOTH = frozenset({INTERNAL, CLIENT})
RECORD_TYPES = (
	RecordType("File", "file", "file_name", None, True, BOTH, number=False),
	RecordType("Whiteboard", "board", "title", None, True, BOTH),
	RecordType("Project Document", "document", "title", "status", False, BOTH),
	RecordType("RFI", "question", "subject", "status", False, BOTH),
	RecordType("Submittal", "review", "title", "status", False, BOTH),
	RecordType("Variation Order", "change", "title", "stage", False, BOTH),
	RecordType("CAD Drawing", "drawing", "title", None, False, frozenset({INTERNAL})),  # no client reads drawings
	# P3-78 (§3.14): an approval request, through its own read rule; the chip names its record (VO-0007), not the hash
	RecordType("Approval Request", "approval", "subject_title", "status", False, BOTH, number=False,
		reference="subject_name"),
)
FILE_COLUMNS = ("file_url", "file_size", "owner", "is_private", "is_folder", "cc_project", "cc_client_visible",
	"cc_trashed", "cc_version_of", "attached_to_doctype", "attached_to_name", "cc_rev", "content_hash")


def by_doctype() -> dict:
	return {t.doctype: t for t in RECORD_TYPES}


def allowed(audience: str, mode: str | None = None) -> list:
	"""The types a room of ``audience`` may tag, in the picker's order. ``mode`` "advanced" offers every one; anything
	else is Simple (D-154), which offers files and Canvas boards only. A view choice: it only narrows."""
	return [t for t in RECORD_TYPES if audience in t.audiences and (mode == "advanced" or t.simple)]


def audience_reads(audience: str, doc) -> bool:
	"""Whether every reader of a room of ``audience`` may read ``doc`` now: the team reads every record of its project;
	the project's clients only what the team shared, while its portal section is on (§3.5, §14.4 row 2)."""
	if audience == INTERNAL:
		return True
	if audience == CLIENT:
		project = doc.get("cc_project") if doc.doctype == "File" else doc.get("project")
		return client_may_see(doc) and client_section_open(doc.doctype, project)
	return False  # Partner: P3-32 (D-444)


def resolve(doctype: str, name: str, ctx) -> dict | None:
	"""One card for ``ctx.user``, or None."""
	return cards(ctx, [(doctype, name)]).get((doctype, name))


def cards(ctx, pairs, project: str | None = None) -> dict:
	"""{(doctype, name): card} of the ``pairs`` ``ctx.user`` may read; the others are left out. One query (see _rows
	for the one configuration that costs more). ``project``: only records and files of that project (a send's check).
	Without ``project`` each answer is kept in ``ctx.memo`` for the page, so a second part asking for the same records
	reads nothing (P3-69: the design event cards and the tags of one page)."""
	types = by_doctype()
	wanted = {}
	for doctype, name in pairs:
		if doctype in types and isinstance(name, str) and name:
			wanted.setdefault(doctype, []).append(name)
	if project is not None:
		return _cards(ctx, wanted, project)
	missing = {d: [n for n in dict.fromkeys(names) if (CARD, d, n, ctx.user) not in ctx.memo]
		for d, names in wanted.items()}
	found = _cards(ctx, {d: names for d, names in missing.items() if names})
	for d, names in missing.items():
		for n in names:
			ctx.memo[(CARD, d, n, ctx.user)] = found.get((d, n))
	return {(d, n): ctx.memo[(CARD, d, n, ctx.user)] for d, names in wanted.items() for n in names
		if ctx.memo[(CARD, d, n, ctx.user)]}


def _cards(ctx, wanted: dict, project: str | None = None) -> dict:
	if not wanted:
		return {}
	types = by_doctype()
	wanted = {d: list(dict.fromkeys(n)) for d, n in wanted.items()}
	rows = _rows(ctx, wanted, project)
	out = {}
	files = [r for r in rows if r.dt == "File"]
	if "File" in wanted:
		from construction_core.discuss.parts.attachments import readable_files

		readable, _revs = readable_files(ctx, [r.name for r in files], rows=[_file_row(r) for r in files])
		for n in wanted["File"]:
			ctx.memo.setdefault(("File", n, ctx.user), False)
		out.update({("File", n): file_card(f) for n, f in readable.items()})
	found = {(r.dt, r.name) for r in rows if r.dt != "File"}
	for doctype, names in wanted.items():
		if doctype == "File":
			continue
		for n in names:
			ctx.memo[(doctype, n, ctx.user)] = (doctype, n) in found
	for r in rows:
		if r.dt != "File":
			out[(r.dt, r.name)] = record_card(types[r.dt], r)
	return out


def record_card(t: RecordType, r) -> dict:
	"""What a viewer sees of a record they read: its type, title, state and number, and ``_ref`` for respond()."""
	return {"_ref": (t.doctype, r.name), "type": t.key, "doctype": t.doctype, "name": r.name,
		"title": r.title or r.name, "state": r.state or None,
		"number": r.get("number") if t.reference else r.name if t.number else None,
		"simple": t.simple, "section": CLIENT_SECTION.get(t.doctype)}


def file_card(f) -> dict:
	"""A file's card: its name and address, never the File's own id (P3-07, SEC-4)."""
	return {"_ref": ("File", f.name), "type": "file", "doctype": "File", "title": f.file_name, "state": None,
		"number": None, "url": f.file_url, "size": f.file_size, "simple": True, "section": CLIENT_SECTION["File"]}


def _rows(ctx, wanted: dict, project: str | None = None) -> list:
	"""Every wanted record the viewer reads, and every wanted File row (checked after, in memory), in one statement.

	A record type's rows are its own list predicate as the viewer: the role's read at permlevel 0, limited to the
	viewer's own records when that read is "Only if Creator" (if_owner), and the project predicate Frappe ANDs into
	every list (permissions.project_scoped: membership, the client rules, the portal and section switches, read once
	per request under switches_once). Frappe's list would also read the viewer's DocShares, one query per type; a share
	here only ever names a project member, who reads the record without it (permissions.validate_share), and a stale
	share never widens a card: the answer is never wider than has_permission, which test_discuss_refs holds equal.
	A viewer with User Permission rows on any doctype but Construction Project (which project_scoped covers) is read
	through Frappe's own list instead, one get_list per type (with its DocShare read): only in that configuration."""
	from frappe.permissions import get_role_permissions, get_user_permissions

	from construction_core.permissions import project_scoped

	selects, values, listed = [], {"cc_ref_project": project}, []
	narrowed = bool(set(get_user_permissions(ctx.user)) - {"Construction Project"})
	nulls = ", ".join(f"null as {c}" for c in FILE_COLUMNS)
	for i, t in enumerate(RECORD_TYPES):
		names = wanted.get(t.doctype)
		if not names or t.doctype == "File":
			continue
		if narrowed:
			listed += _listed(ctx, t, names, project)
			continue
		perms = get_role_permissions(t.doctype, user=ctx.user)
		if not perms.get("read"):
			continue  # no role of the viewer reads this type: none of its records is theirs
		where = [project_scoped(ctx.user, t.doctype)]
		if "read" in (perms.get("if_owner") or {}):  # "Only if Creator": the viewer's own records
			where.append(f"`owner` = {frappe.db.escape(ctx.user)}")
		if project:
			where.append("`project` = %(cc_ref_project)s")
		state = f"`{t.state}`" if t.state else "null"
		number = f"`{t.reference}`" if t.reference else "null"
		values[f"cc_ref_{i}"] = tuple(names)
		selects.append(f"select {frappe.db.escape(t.doctype)} as dt, `name`, `{t.title}` as title, {state} as state, "
			f"{number} as number, {nulls} from `tab{t.doctype}` where `name` in %(cc_ref_{i})s"
			+ "".join(f" and ({w})" for w in where if w))
	if wanted.get("File"):
		columns = ", ".join(f"f.{c}" for c in FILE_COLUMNS)
		values["cc_ref_files"] = tuple(wanted["File"])
		selects.append(f"select 'File' as dt, f.name, f.file_name as title, null as state, null as number, {columns} "
			"from `tabFile` f where f.name in %(cc_ref_files)s" + (" and f.cc_project = %(cc_ref_project)s" if project else ""))
	rows = frappe.db.sql(" union all ".join(selects), values, as_dict=True) if selects else []
	return [*rows, *listed]


def _listed(ctx, t: RecordType, names: list, project: str | None) -> list:
	filters = {"name": ["in", names], **({"project": project} if project else {})}
	try:
		found = frappe.get_list(t.doctype, filters=filters, fields=["name", f"{t.title} as title",
			*([f"{t.state} as state"] if t.state else []), *([f"{t.reference} as number"] if t.reference else [])],
			limit=len(names), user=ctx.user)
	except frappe.PermissionError:
		frappe.clear_last_message()
		return []
	return [frappe._dict(r, dt=t.doctype, state=r.get("state")) for r in found]


def _file_row(r) -> frappe._dict:
	return frappe._dict({"name": r.name, "file_name": r.title, **{c: r.get(c) for c in FILE_COLUMNS}})
