"""P3-16 (R-13; D-192, D-209): the mails of onboarding, and whether mail can be sent at all.

Every onboarding mail carries a link or a code and nothing else typed by a guest; it is escaped by its template and
redacted from the Email Queue once sent (`redact_message_after_send`).
"""

import unicodedata

import frappe
from frappe import _
from frappe.utils import escape_html, format_datetime, get_fullname

# P3-44 (D-298): the product's name in every mail. The one value for the core's mails; the shell takes its default
# from here (the core never imports the shell). A firm never renames the product (D-445).
PRODUCT_NAME = "Keystone"
# R-30 (D-401…D-404): Keystone leads only until the firm's name is set; then the firm leads and a small "Powered by"
# credit names the product. The credit follows the firm's name and has no setting that removes it (D-404).


def mail_ready() -> bool:
	"""True when Frappe itself would find an outgoing account: the same lookup frappe.sendmail uses (D-209)."""
	from frappe.email.doctype.email_account.email_account import EmailAccount

	try:
		return bool(EmailAccount.find_one_by_filters(enable_outgoing=1, default_outgoing=1)
			or EmailAccount.find_from_config())
	except Exception:
		return False


def brand() -> str:
	"""The company's name, the one helper every reader uses: the Brand page's (P3-45, D-344), else site config
	cc_company_name (set at go-live, D-210), else "" when not set: the words then name the project team. Never Frappe's
	own app name, which reads "Frappe" by default."""
	from construction_core.brand import stored

	name = stored()["company_name"] or frappe.conf.get("cc_company_name") or ""
	# The name is shown in titles, mails and a tab icon: a control character or a lone surrogate (which a page cannot be
	# encoded with) is dropped. Every other character stays, joiners included: some scripts need them.
	name = "".join(ch for ch in str(name) if unicodedata.category(ch) not in ("Cc", "Cs"))
	return name.strip()[:80]


def brand_name() -> str:
	"""The name that leads: the firm's, or the product's until the firm's is set (D-403)."""
	return brand() or PRODUCT_NAME


def credited() -> bool:
	"""Whether the small "Powered by" credit shows: once a firm's name leads (D-402, D-404)."""
	return bool(brand())


def credit_html() -> str:
	"""The small "Powered by Keystone" line that ends every mail once a firm's name leads (D-402, D-404); "" until then.
	Every mail the core sends takes it from here: the onboarding templates through `_brand_args`, the two-step notice and
	the client's @mention email by adding it to their body."""
	if not credited():
		return ""
	text = escape_html(_("Powered by {0}").format(PRODUCT_NAME))
	return f'<p style="margin: 24px 0 0; font-size: 12px; color: #6b6b6b;">{text}</p>'


def _brand_args() -> dict:
	"""What every mail's template may name: the company (brand, "" when not set), the product, the name that leads,
	whether the credit shows (D-403) and the credit's line itself."""
	return {"brand": brand(), "product": PRODUCT_NAME, "brand_name": brand_name(), "credit": credited(),
		"credit_html": credit_html()}


def logo_url() -> str:
	"""P3-45: the firm's logo as an absolute address for a mail's head, "" when none (the head as before). The client
	onboarding mails show it: the invitation, the sign-up code and the access-added note."""
	from frappe.utils import get_url

	from construction_core.brand import stored

	logo = stored()["logo"]
	return get_url(logo) if logo else ""


def staff_invite_subject() -> str:
	"""D-401: "You're invited to join Firm", the firm leading and Keystone not named; until a firm is set (D-403),
	"You're invited to join the team on Keystone"."""
	company = brand()
	if company:
		return _("You're invited to join {0}").format(company)
	return _("You're invited to join the team on {0}").format(PRODUCT_NAME)


def first_name(user: str | None) -> str:
	return (get_fullname(user) or "").split(" ")[0] if user else ""


def send_invite(invite, link: str) -> bool:
	"""Queue an invitation mail to its bound address; Frappe sends it after the commit (v16: now=True queues). False
	when it cannot even be queued, logged with a fixed text: a traceback would hold the link (P3-16 audit S1)."""
	try:
		frappe.sendmail(
			recipients=[invite.email],
			subject=_("You're invited to follow your project online"),
			template="cc_invite",
			args={"link": link, "name": invite.full_name or "", "inviter": first_name(invite.invited_by),
				**_brand_args(), "logo_url": logo_url(), "expires": format_datetime(invite.expires_on, "d MMMM, h:mm a")},
			now=True,
			redact_message_after_send=True,
			reference_doctype="Access Invite",
			reference_name=invite.name,
		)
		return True
	except Exception:
		frappe.log_error(title="construction_core: an invitation mail could not be queued",
			message=f"Access Invite {invite.name}", defer_insert=True)
		return False


def send_staff_invite(invite, link: str) -> bool:
	"""P3-21 (D-235): a team invitation, to its bound address; the link opens without a code. P3-54 (D-346): the
	owner's invitation (kind Owner) is the same mail with its own words."""
	try:
		frappe.sendmail(
			recipients=[invite.email],
			subject=staff_invite_subject(),
			template="cc_owner_invite" if invite.kind == "Owner" else "cc_staff_invite",
			args={"link": link, "name": invite.full_name or "", "inviter": first_name(invite.invited_by),
				**_brand_args(), "role": invite.role, "expires": format_datetime(invite.expires_on, "d MMMM, h:mm a")},
			now=True,
			redact_message_after_send=True,
			reference_doctype="Access Invite",
			reference_name=invite.name,
		)
		return True
	except Exception:
		frappe.log_error(title="construction_core: a team invitation mail could not be queued",
			message=f"Access Invite {invite.name}", defer_insert=True)
		return False


def send_code(invite, email: str, code: str, request: str | None = None) -> bool:
	"""Queue a sign-up code to the address it proves; nothing else in the mail (P3-17, D-214). It names the person's
	Access Request, so the invitation's own mail status stays the invitation mail's (P3-18 audit S2)."""
	try:
		frappe.sendmail(
			recipients=[email],
			subject=_("Your code to finish joining"),  # never the code itself: a subject may be kept unredacted
			template="cc_join_code",
			args={"code": code, **_brand_args(), "logo_url": logo_url(), "minutes": 15},
			now=True,
			redact_message_after_send=True,
			reference_doctype="Access Request" if request else "Access Invite",
			reference_name=request or invite.name,
		)
		return True
	except Exception:
		frappe.log_error(title="construction_core: a sign-up code mail could not be queued",
			message=f"Access Invite {invite.name}", defer_insert=True)
		return False


def _queue(request, email: str, subject: str, template: str, args: dict, what: str) -> bool:
	try:
		frappe.sendmail(recipients=[email], subject=subject, template=template, args={**_brand_args(), **args},
			now=True, redact_message_after_send=True, reference_doctype="Access Request", reference_name=request.name)
		return True
	except Exception:
		frappe.log_error(title=f"construction_core: {what} mail could not be queued",
			message=f"Access Request {request.name}", defer_insert=True)
		return False


def send_finish(request, email: str, link: str) -> bool:
	"""P3-18 (D-220): a manager approved this person; the single-use link to finish joining, to their address only."""
	return _queue(request, email, _("You're approved: finish joining your project"), "cc_join_finish",
		{"link": link, "hours": 48}, "a finish-joining")


def send_access_added(request, email: str) -> bool:
	"""P3-18 (D-220): an existing client was approved on an open link; their account now has the project."""
	from frappe.utils import get_url

	return _queue(request, email, _("A project was added to your account"), "cc_access_added",
		{"link": get_url("/portal"), "logo_url": logo_url()}, "an access-added")


def delivery(invite_name: str) -> str | None:
	"""What became of the newest mail of an invitation: Sent, Failed, or Queued while Frappe still tries (S2)."""
	status = frappe.get_all("Email Queue", filters={"reference_doctype": "Access Invite", "reference_name": invite_name},
		order_by="creation desc", limit=1, pluck="status")
	if not status:
		return None
	return {"Sent": "Sent", "Error": "Failed", "Cancelled": "Failed"}.get(status[0], "Queued")
