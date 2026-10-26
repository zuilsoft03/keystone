"""The statements a client accepts and signs under (approvals design §3.5 items 2 and 4, §5; P3-78 M2).

The texts are code constants with a version id: the portal agreement, the locked line above the signing box for each kind
of record, and the location notice. A new wording is a new version (a translation too, approved by the firm's lawyer).
``agree`` records that an approver accepted the current agreement for a project: an ``agreed`` chain event with the
version and the SHA-256 of the text as filled in, and the text mailed to them. ``decide`` checks the same version and
text inside its lock (``accepted``), so a changed contract reference or firm name asks again.
"""

import json
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import getdate

from construction_core.approvals import api, canonical, log, read, subjects
from construction_core.onboarding.mail import brand_name
from construction_core.permissions import refuse_closed

LANGUAGE = "en"
VERSION = "agreement-1"
AGREEMENT = ("I agree to give approvals for {project} through this portal. My account is personal. I confirm {client} has "
	"authorised me to give these approvals. An approval I give here is my written approval and signature under our "
	"contract with {firm} ({contract}).")
LINES_VERSION = "lines-1"
LINE = "By signing and clicking Sign and approve, {what} This is your written approval and signature under your contract " \
	"with {firm}."
NOTICE_VERSION = "location-1"
NOTICE = ("Share this device's location with my answer. Your browser asks you first. The location is rounded to about 1 "
	"km and kept with this answer's evidence for the team's managers. Leaving this unticked does not change your answer.")


def agreement_text(project: str) -> str:
	p = frappe.db.get_value(api.PROJECT, project, ["project_name", "cc_client_legal_name", "cc_contract_document",
		"cc_contract_date", "cc_contract_clause"], as_dict=True)
	day = getdate(p.cc_contract_date) if p.cc_contract_date else None
	contract = ", ".join(x for x in (p.cc_contract_document, day and f"{day.day} {day:%B %Y}", p.cc_contract_clause) if x)
	return AGREEMENT.format(project=p.project_name, client=p.cc_client_legal_name, firm=brand_name(), contract=contract)


def accepted(project: str, user: str) -> int | None:
	"""The seq of the user's agreed event in this project when it holds the current version and text, else None."""
	rows = frappe.get_all(log.EVENT, filters={"project": project, "kind": "agreed", "actor": user},
		fields=["seq", "canonical"], order_by="seq desc", limit=1)
	body = json.loads(rows[0].canonical)["body"] if rows else {}
	ok = body.get("version") == VERSION and body.get("text_sha256") == canonical.sha256(agreement_text(project))
	return rows[0].seq if ok else None


def _change(currency: str, cost: str, days: str) -> str:
	amount, days = Decimal(cost or "0"), int(days or 0)
	if not amount and not days:
		return "no change in cost or time"
	money = (f"added cost {currency} {amount:,.2f}" if amount > 0 else f"a credit of {currency} {-amount:,.2f}"
		if amount else "no change in cost")
	time = (f"{days} more day{'s' if days != 1 else ''}" if days > 0
		else f"{-days} fewer day{'s' if days != -1 else ''}" if days else "no change in time")
	return f"{money} and {time}"


def lines(r) -> dict[str, str]:
	"""The locked line (§5) for a request, by the option it is signed for: each option's key for a Decision, else
	"record". Title first and reference second, from the frozen terms."""
	terms, ref, firm = json.loads(r.snapshot)["terms"], r.subject_name, brand_name()
	if r.subject_doctype == subjects.DECISION:
		return {o["key"]: LINE.format(firm=firm, what=f'you choose {o["label"]} for "{terms["title"]}" ({ref}) exactly as '
			f'shown: {_change(terms["currency"], o["cost_difference"], o["time_difference"])}.') for o in terms["options"]}
	if r.subject_doctype == subjects.VO:
		change = _change(terms["currency"], terms["total"], terms["days"])
		what = f'you approve "{terms["title"]}" ({ref}) exactly as shown: {change}.'
	else:  # a Submittal by its name and revision number, a Document by its number and revision
		ref = terms.get("number") or ref
		what = f'you approve "{terms["title"]}" ({ref}, revision {terms.get("revision") or "-"}) exactly as shown.'
	return {"record": LINE.format(firm=firm, what=what)}


@frappe.whitelist(methods=["POST"])
def agree(request: str, version: str, password: str | None = None) -> dict:
	"""The approver accepts the current agreement for the request's project (§3.5 item 2): their own browser session, a
	confirmed approver with no re-confirmation due, the password once (the step's own counter), then the chain event and
	the mail."""
	from construction_core.approvals import answer, credentials  # here: answer imports this module

	user = answer.answerer()
	r = read.readable(request)
	if not r:
		raise frappe.DoesNotExistError(_("Not found"))
	refuse_closed(r.project)
	if version != VERSION:
		frappe.throw(_(answer.WORDS["PageOutdated"]), answer.PageOutdated)

	def _agree() -> dict:
		log.lock(r.project)
		if not api.approvers(r.project).get(user):
			frappe.throw(_(answer.WORDS["NotApprover"]), answer.NotApprover)
		if credentials.must_reset(user):
			frappe.throw(_(credentials.MUST_RESET), credentials.MustReset)
		answer.check_password(user, password)
		if not accepted(r.project, user):
			text = agreement_text(r.project)
			log.append_event(r.project, "agreed", body={"user": user, "version": VERSION, "language": LANGUAGE,
				"text_sha256": canonical.sha256(text)})
			name = frappe.db.get_value(api.PROJECT, r.project, "project_name")
			api._mail([api._email(user)], _("Your portal agreement for {0}").format(name),
				[_("You accepted this agreement in the project portal:"), text])
		return {"version": VERSION, "accepted": True}

	return log.retry_once(_agree)
