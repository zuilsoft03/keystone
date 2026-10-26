"""Credential events and re-confirmation (approvals design §4.5; P3-78 M7; threat T7).

- **Events**: a client account's password set by someone else (User before_validate, before Frappe's validate clears
  new_password), a self-service change or reset (the ``update_password`` wrap), a two-step change or ``reset_for``
  (two_step._after_change) and a sign-in address rename (User before_rename) are each a ``credential`` chain event in
  every project where the account is a member (the holder's own change: in those that have a chain), mailed to the
  account's address at once (the old one for a rename). The same change carries one ``change_id`` in each project. An
  API key never reaches a client account (accounts.guard).
- **Re-confirmation** (``pending``): after a change by someone else, ``decide`` and ``agree`` refuse the account until its
  holder sets a new password through a link ``send_reset_link`` mailed to the address verified before the change. There
  is no time window. A change with the old password does not count: whoever set the password knows it.
- **A legitimate address change** (``confirm_address``): a second staff member confirms the client's identity with proof;
  the link then goes to the new address.
- ``needs_reconfirmation(request)``: an answer recorded under a change found later reads "Needs re-confirmation"; the
  staff gate calls it.
"""

import json
import secrets

import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils.data import sha256_hash

from construction_core.approvals import api, log

# a change made by someone else that only the holder's own reset ends
CHANGES = ("password_set", "password_changed", "two_step", "rename")
NOTE_MAX = 1000
MUST_RESET = "Must reset password before approving"
# The account-level marker of such a change, keyed by the account: it holds for a new account and one in no project,
# which have no chain to write to. A DefaultValue under its own parent, as Frappe's two-factor keeps its secrets: no
# route a user has writes it (set_session_default_values writes only the session user's own defaults).
MARKS = "__cc_credential_marks"


class MustReset(frappe.PermissionError):
	"""Must reset password before approving (§4.5)."""


def _client(user) -> bool:
	return frappe.db.get_value("User", user, "user_type") == "Website User"


def _projects(user) -> list[str]:
	"""In name order, the lock order of a change written to several chains."""
	return sorted(set(frappe.get_all("Project Member", filters={"parenttype": api.PROJECT, "user": user},
		pluck="parent")))


def changed(account: str, change: str, by_other: bool | None = None, address: str | None = None, **extra) -> None:
	"""One credential event per member project of a client account; staff accounts answer nothing (§6). ``address``: where
	the event's mail goes and, for a change by someone else, the address verified before it."""
	if not _client(account):
		return
	by = frappe.session.user
	other = by != account if by_other is None else by_other
	address = address or api._email(account)
	body = {"user": account, "change": change, "by": by, "by_other": "1" if other else "0", "address": address,
		"changed_at": log._now(), "change_id": secrets.token_hex(8), **extra}
	if other and change in CHANGES:
		mark(extra.get("renamed_to") or account)
	# A change by someone else goes to every member project, so no later chain misses it (no time window). The holder's
	# own goes only where a chain exists: those include every project a pending change reached, and a project with no
	# approval records stays deletable (D-092) when a client changes their own password.
	for project in _projects(account):
		if other or frappe.db.exists(log.EVENT, {"project": project}):
			log.append_event(project, "credential", body=body)
	words = {"password_set": _("Your password for the project portal was set by {0}.").format(by),
		"password_changed": _("Your password for the project portal was changed."),
		"password_reset": _("Your password for the project portal was reset through a link sent to you."),
		"rename": _("Your sign-in address for the project portal was changed to {0} by {1}.").format(
			extra.get("renamed_to"), by)}.get(change)  # two-step mails its own notice; the others are staff steps
	if words:
		api._mail([address], _("Your sign-in details changed"), [words, _("If this was not you, tell the team now.")]
			+ ([_("Before you approve anything in the portal, set a new password yourself through the link the team "
				"sends you.")] if body["by_other"] == "1" else []))


def _bodies(user) -> list[dict]:
	"""The account's credential events, one per change (each is written once per project), oldest change first."""
	seen = {}
	# shortcut: reads every credential event of the site; index them by account once there are thousands
	for text in frappe.get_all(log.EVENT, filters={"kind": "credential"}, pluck="canonical", order_by="seq asc"):
		body = json.loads(text)["body"]
		if user in (body.get("user"), body.get("renamed_to")):
			seen.setdefault(body["change_id"], body)
	return sorted(seen.values(), key=lambda b: b["changed_at"])


def pending(user: str, at: str | None = None) -> dict | None:
	"""The first change by someone else that the holder has not yet followed with their own reset through a link sent to
	the address verified before it (§4.5), as it stood at ``at`` (canonical UTC text; None: now)."""
	first = None
	for b in _bodies(user):
		if at and b["changed_at"] > at:
			break
		if b["change"] in CHANGES and b["by_other"] == "1":
			first = first or b
		elif b["change"] == "password_reset" and b.get("verified") == "1":
			first = None
	return first


def mark(account: str) -> None:
	frappe.defaults.set_default(account, str(log._now()), MARKS)


def must_reset(user: str) -> bool:
	return bool(pending(user) or frappe.db.get_value("DefaultValue", {"parent": MARKS, "defkey": user}))


def verified_address(user: str) -> str:
	"""Where the reset link goes: the address verified before the first unresolved change, or the one a second staff
	member confirmed after it; with nothing unresolved, the account's own."""
	first = pending(user)
	if not first:
		return api._email(user)
	confirmed = [b for b in _bodies(user) if b["change"] == "address_confirmed" and b["changed_at"] > first["changed_at"]]
	return confirmed[-1]["address"] if confirmed else first["address"]


def last_change(user: str) -> dict:
	"""The account's latest credential event, for the answer's evidence (§4.1)."""
	bodies = _bodies(user)
	return {k: bodies[-1][k] for k in ("change_id", "change", "changed_at", "by_other")} if bodies else {}


def needs_reconfirmation(request: str) -> bool:
	"""Whether a request's answer was given while its approver had an unresolved change by someone else, including one
	recorded after the answer with an earlier time (§4.5: "Needs re-confirmation"; it does not satisfy the gate)."""
	from construction_core.approvals.receipts import decider_of  # here: receipts imports this module

	rows = frappe.get_all(log.EVENT, filters={"request": request, "kind": ("in", ("approved", "returned"))},
		fields=["actor", "canonical"], order_by="seq desc", limit=1)
	return bool(rows) and bool(pending(decider_of(rows[0]), json.loads(rows[0].canonical)["at"]))


# --- hooks ----------------------------------------------------------------------------------------------------------


def on_user_before_validate(doc, method=None):
	"""User before_validate: a password set on the form (a System Manager's, D-204's support path), read before Frappe's
	validate clears new_password. A new account has no project yet, so no chain to write to: one created with a password
	is marked, whatever its type (its user_type is set in validate, after this)."""
	if not doc.get("new_password"):
		return
	if doc.is_new():
		if frappe.session.user != doc.name:
			mark(doc.name)
		return
	changed(doc.name, "password_set" if frappe.session.user != doc.name else "password_changed")


def on_user_rename(doc, method=None, old=None, new=None, merge=False):
	"""User before_rename: a sign-in address changed, mailed to the old address, which stays the verified one."""
	if old and new and old != new:
		changed(old, "rename", renamed_to=new)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_password(new_password: str, logout_all_sessions: int = 0, key: str | None = None,
		old_password: str | None = None):
	"""Frappe's update_password, recorded once its own checks pass: a reset by key, or a change with the old password. A
	key that send_reset_link mailed is the holder's own reset (``verified``), which ends a re-confirmation."""
	from frappe.core.doctype.user.user import update_password as frappe_update_password

	key_sha = sha256_hash(key) if isinstance(key, str) and key else None
	account = frappe.db.get_value("User", {"reset_password_key": key_sha}) if key_sha \
		else (frappe.session.user if old_password else None)  # read before Frappe spends the key
	out = frappe_update_password(new_password, logout_all_sessions, key, old_password)
	if account and account != "Guest" and frappe.local.response.get("http_status_code") != 410:
		sent = [b for b in _bodies(account) if b["change"] == "reset_sent"]
		verified = bool(key_sha and sent and sent[-1]["key_sha256"] == key_sha)
		changed(account, "password_reset" if key_sha else "password_changed", by_other=False,
			verified="1" if verified else "0")
		if verified:  # the holder's own reset through the link the team sent: the only way the marker ends
			frappe.defaults.clear_default(key=account, parent=MARKS)
	return out


# --- staff ----------------------------------------------------------------------------------------------------------


def _contact(project, member):
	"""A client contact of the project, for its managers (manage_clients) or a System Manager. No project lock: the
	events lock every member project in name order."""
	doc = frappe.get_doc(api.PROJECT, project) if isinstance(project, str) and frappe.db.exists(api.PROJECT, project) \
		else None
	if not doc:
		raise frappe.DoesNotExistError(_("Not found"))
	frappe.has_permission(api.PROJECT, "read" if "System Manager" in frappe.get_roles() else "manage_clients", doc=doc,
		throw=True)
	return api._contact_row(doc, member).user


def masked(address: str) -> str:
	local, _sep, domain = (address or "").partition("@")
	return f"{local[:1]}***@{domain}" if domain else "***"


@frappe.whitelist(methods=["POST"])
def send_reset_link(project: str, member: str) -> dict:
	""""Send reset link" (§4.5): Frappe's own single-use reset key, mailed by us to the address verified before the
	change and recorded with the key's hash, so its use is known to be the holder's own reset."""
	account = _contact(project, member)
	address = verified_address(account)
	link = frappe.get_doc("User", account)._reset_password()
	changed(account, "reset_sent", address=address, key_sha256=sha256_hash(link.split("key=", 1)[1].split("&")[0]))
	api._mail([address], _("Set a new password"), [_("Before you approve anything in the project portal, set a new "
		"password yourself. The link works once.")], link=(link, _("Set a new password")))
	return {"sent_to": masked(address)}


@frappe.whitelist(methods=["POST"])
def confirm_address(project: str, member: str, proof_file: str, note: str) -> dict:
	"""A legitimate address change (§4.5): a second staff member, not the one who renamed the account, confirms the
	client's identity with proof (a letter or a call note, a File of this project, frozen); the reset link then goes to
	the new address."""
	account = _contact(project, member)
	first = pending(account)
	rename = next((b for b in reversed(_bodies(account)) if b["change"] == "rename"
		and b["changed_at"] >= first["changed_at"]), None) if first else None
	if not rename:
		frappe.throw(_("This account has no address change waiting for confirmation."))
	if rename["by"] == frappe.session.user:
		raise frappe.PermissionError(_("A second staff member confirms an address change, not the one who made it."))
	note = cstr(note).strip()[:NOTE_MAX]
	if not note:
		frappe.throw(_("Say how you confirmed the client's identity."))
	sha, name = api._freeze_file(project, proof_file)
	changed(account, "address_confirmed", proof=sha, proof_name=name, note=note)
	return {"address": api._email(account)}
