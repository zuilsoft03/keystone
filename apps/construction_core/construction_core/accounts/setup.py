"""P3-51, P3-52, P3-54 (docs/design/phase-3.3-firm-setup.md §4 Stage B, §5, §6; D-344, D-346, D-347): the set-up wizard.

Firm Settings holds the firm's details and each step's state (W1…W12). Every whitelisted body checks System Manager
(T7, T9); `mark` is the helper the other server modules call once they have checked their own right. A step the server
proves (the mail code W3, the owner's join W4, a backup W6, the defaults W7, the team invitations W9) is marked done only
by the module that proves it; the screens may mark done only the steps whose completion is their own act (CLIENT_DONE).
Set-up is finished when W1 is done and every other step but the hidden ones is done or skipped.

The owner's account (W4, D-346, T1): only Administrator invites it, only before set-up is finished, one open at a time,
as an Access Invite of kind Owner through the same join page as a team invitation; the join page grants exactly
join.OWNER_ROLES and checks again at finish that the inviter is Administrator and set-up is unfinished.
"""

import secrets

import frappe
from frappe import _
from frappe.utils import add_days, cint, format_datetime, now_datetime

from construction_core import brand
from construction_core.onboarding import invites

DOCTYPE = "Firm Settings"
STEPS = tuple(f"W{i}" for i in range(1, 13))
STATES = ("done", "skipped")
HIDDEN = ("W11",)  # partner companies come after go-live (D-444)
CLIENT_DONE = ("W2", "W5", "W8", "W10")  # "Keep Keystone", the two-step switch, the first project, the client dialog
FIRM = ("legal_name", "tin", "address", "phone", "privacy_email")
DEFAULTS = ("default_vat", "default_retention", "default_withholding")
LATER = "cc_setup_later"  # a per-user default: "Finish later" keeps this System Manager on the dashboard (T8)
OWNER_DAYS = 7


def _only():
	frappe.only_for("System Manager")


def finished() -> bool:
	# not get_single_value: it casts an empty Datetime to now
	return bool(frappe.db.get_singles_dict(DOCTYPE).get("setup_finished_on"))


def later(user: str) -> bool:
	return bool(cint(frappe.defaults.get_user_default(LATER, user)))


def _open_owner():
	"""The owner invitation that still works, or None: an expired one never blocks a new one."""
	for inv in frappe.get_all("Access Invite", filters={"kind": "Owner", "status": "Active"},
			fields=["name", "email", "full_name", "expires_on", "status"], order_by="creation desc"):
		if invites.effective_status(inv) == "Active":
			return inv
	return None


def _state() -> dict:
	doc = frappe.get_single(DOCTYPE)
	rows = {r.step: r for r in doc.steps}
	steps = {s: {"state": rows[s].state, "by": rows[s].marked_by, "on": str(rows[s].marked_on or "")} if s in rows
		else {"state": "", "by": None, "on": ""} for s in STEPS}
	done = finished()
	owner = None if done else _open_owner()  # once finished, the join page refuses it
	return {"finished": done, "steps": steps,
		"firm": {**{f: doc.get(f) or "" for f in FIRM}, "company_name": brand.stored()["company_name"]
			or frappe.conf.get("cc_company_name") or ""},  # the install's pre-fill until the owner saves (D-218)
		"defaults": {f: doc.get(f) for f in DEFAULTS},
		"owner_invite": {"allowed": frappe.session.user == "Administrator" and not done,
			"open": {"email": owner.email, "full_name": owner.full_name, "expires": format_datetime(owner.expires_on, "d MMMM, h:mm a")} if owner else None},
		"hidden": list(HIDDEN)}


@frappe.whitelist(methods=["GET"])
def state() -> dict:
	_only()
	return _state()


def mark(step: str, state: str, by: str | None = None) -> None:
	"""Record a step's state (no permission check: callers check theirs). A done step is never turned into skipped."""
	if step not in STEPS or state not in STATES:
		frappe.throw(_("Unknown set-up step."))
	doc = frappe.get_doc(DOCTYPE, DOCTYPE, for_update=True)  # one writer at a time: the steps are one table
	row = next((r for r in doc.steps if r.step == step), None)
	if row and row.state == "done" and state == "skipped":
		return
	if not row:
		row = doc.append("steps", {"step": step})
	row.update({"state": state, "marked_by": by or frappe.session.user, "marked_on": now_datetime()})
	doc.save(ignore_permissions=True)  # Firm Settings is System Manager only; every caller checked its right


@frappe.whitelist(methods=["POST"])
def save_firm(company_name=None, legal_name=None, tin=None, address=None, phone=None, privacy_email=None) -> dict:
	"""W1 (D-344): only the fields given; the company name through the Brand page's call. W1 is done once the company
	name and the privacy contact are both set."""
	_only()
	if company_name is not None:
		brand.update(company_name=company_name)
	given = {"legal_name": legal_name, "tin": tin, "address": address, "phone": phone, "privacy_email": privacy_email}
	doc = frappe.get_doc(DOCTYPE, DOCTYPE, for_update=True)
	doc.update({k: v if isinstance(v, str) else str(v) for k, v in given.items() if v is not None})
	doc.save(ignore_permissions=True)  # the role was checked above; validate() checks every value
	if brand.stored()["company_name"] and doc.privacy_email:
		mark("W1", "done")
	return _state()


@frappe.whitelist(methods=["POST"])
def mark_step(step=None, state=None) -> dict:
	"""A screen's Skip, or done for the steps the screen itself completes (CLIENT_DONE). W1 is never skipped."""
	_only()
	if step not in STEPS or step in ("W1", "W12", *HIDDEN) or state not in STATES:
		frappe.throw(_("This step cannot be marked here."))
	if state == "done" and step not in CLIENT_DONE:
		frappe.throw(_("This step is marked done when it is finished."))
	if state == "done" and step == "W8" and not frappe.db.count("Construction Project"):
		frappe.throw(_("Make the first project first."))
	mark(step, state)
	return _state()


@frappe.whitelist(methods=["POST"])
def finish() -> dict:
	"""W12: set-up is finished when W1 is done and every other shown step is done or skipped (§4)."""
	_only()
	doc = frappe.get_doc(DOCTYPE, DOCTYPE, for_update=True)
	settled = {r.step: r.state for r in doc.steps}
	if settled.get("W1") != "done" or any(s not in settled for s in STEPS if s not in ("W1", "W12", *HIDDEN)):
		frappe.throw(_("Finish or skip every step first."))
	if not (brand.stored()["company_name"] and doc.privacy_email):  # W1 stays done if either is cleared later
		frappe.throw(_("Give the company name and the privacy contact first."))
	if not doc.setup_finished_on:
		doc.setup_finished_on = now_datetime()
		doc.save(ignore_permissions=True)
		mark("W12", "done")
	return _state()


@frappe.whitelist(methods=["POST"])
def finish_later() -> dict:
	"""T8: this System Manager is no longer sent to the wizard; the dashboard's checklist stays (F2)."""
	_only()
	frappe.defaults.set_user_default(LATER, 1)
	return {"later": True}


# --- the owner's account (W4, D-346) ---------------------------------------------------------------------------------


def _administrator_before_finish():
	_only()
	if frappe.session.user != "Administrator":
		raise frappe.PermissionError(_("Only Administrator invites the firm's owner."))
	if finished():
		raise frappe.PermissionError(_("Set-up is finished: give System Manager in Desk."))


@frappe.whitelist(methods=["POST"])
def invite_owner(full_name=None, email=None) -> dict:
	"""W4 (T1): an Access Invite of kind Owner to a new address, 7 days, through the join page's team steps."""
	_administrator_before_finish()
	invites._require_mail()
	email = invites._clean_email(email)
	name = invites._plain(full_name)
	if not name:
		frappe.throw(_("Give the owner's name."))
	if email in invites.RESERVED or frappe.db.exists("User", email) or frappe.db.exists("User", {"email": email}):
		frappe.throw(_("{0} already has an account: give it System Manager in Desk instead.").format(email))
	frappe.get_doc(DOCTYPE, DOCTYPE, for_update=True)  # two calls at once: the second sees the first one's invitation
	if _open_owner():
		frappe.throw(_("An owner invitation is already waiting. Take it back first to send a new one."))
	token, mail_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
	inv = frappe.get_doc({"doctype": "Access Invite", "kind": "Owner",
		"role": "Construction Manager",  # the field's default is the client role; the join page grants OWNER_ROLES
		"email": email, "full_name": name, "status": "Active", "expires_on": add_days(now_datetime(), OWNER_DAYS),
		"token_hash": invites.token_hash(token), "mail_token_hash": invites.token_hash(mail_token),
		"invited_by": "Administrator", "mail_state": "Not sent"})
	inv.flags.cc_owner_invite = True  # the one path AccessInvite.validate lets make an Owner invitation
	inv.insert(ignore_permissions=True)  # System Manager-only doctype; the caller is Administrator
	from construction_core.accounts.people import _staff_share

	return {**_staff_share(inv, token, mail_token, 1), "state": _state()}


@frappe.whitelist(methods=["POST"])
def revoke_owner_invite() -> dict:
	"""Take back the waiting owner invitation (a mistyped address), so a new one can be sent."""
	_administrator_before_finish()
	owner = _open_owner()
	if owner:
		inv = frappe.get_doc("Access Invite", owner.name, for_update=True)
		inv.update({"status": "Revoked", "revoked_by": frappe.session.user, "revoked_on": now_datetime()})
		invites._unprove(inv)
		inv.save(ignore_permissions=True)
	return _state()


def seed_privacy() -> None:
	"""Install and the P3-51 patch: the install's privacy contact (site config, D-218) becomes Firm Settings' value."""
	conf = (frappe.conf.get("cc_privacy_email") or "").strip().lower()[:120]
	if invites.SEPARATORS.search(conf) or frappe.utils.validate_email_address(conf) != conf:
		return  # a value the controller refuses would make every later save of Firm Settings fail
	if not frappe.db.get_single_value(DOCTYPE, "privacy_email", cache=False):
		frappe.db.set_single_value(DOCTYPE, "privacy_email", conf)
