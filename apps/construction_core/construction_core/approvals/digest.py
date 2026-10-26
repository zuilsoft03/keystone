"""The daily job of the approvals ledger (design §4.6, §4.8, §4.9; P3-81), named in hooks.py. In order:

1. ``build``: a project's chain gets a ``build`` event when the app versions (describe.fingerprint) differ from its last.
2. ``verify.run``: the whole check; on a failure it writes ``verify_failed`` and mails the mailbox itself.
3. The digest to the evidence mailbox, every day even with no events (a missing day is visible): each project's head and
   the last 24 hours' canonical lines (commitments, never raw personal data), with the heads as ``heads.json`` (the
   restore drill's input). After the send, one ``anchor`` event per chained project: its head, the recipient, the Message-ID.
4. Approver heads: each confirmed approver of a project with a non-system event in the last 24 hours (none of a
   request in internal review, §14.3) gets its head
   (hashes only). System events never count (an anchor would start a mail loop), and no chain event is written for
   these mails (a receipt event would count too).
5. ``retention.run``: the personal detail whose retention has ended (§4.8).

Each step is committed on its own and has its own error log, so one failure stops no other step; the digest goes out even if a step
before it failed. The mail goes through ``receipts._deliver`` (an Email Queue row, sent now, its Message-ID read back).
"""

import json
from datetime import timedelta
from html import escape

import frappe
from frappe import _

from construction_core.approvals import api, describe, log, receipts

DAY = timedelta(hours=24)


def heads() -> dict[str, dict]:
	"""{project: {"seq", "hash"}} of every chain."""
	rows = frappe.db.sql("""select e.project, e.seq, e.hash from `tabApproval Event` e
		join (select project, max(seq) top from `tabApproval Event` group by project) h
		on h.project = e.project and h.top = e.seq order by e.project""", as_dict=True)
	return {r.project: {"seq": str(r.seq), "hash": r.hash} for r in rows}


def daily() -> None:
	# a commit after each step, never a savepoint: sending mail commits (Frappe's SendMailContext), which drops one
	for step in (_builds, _verify, _digest, _approver_heads, _retention):
		try:
			step()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"construction_core: the approvals daily job failed at {step.__name__}")


def _builds() -> None:
	now = describe.fingerprint()
	for project in heads():
		last = frappe.get_all(log.EVENT, filters={"project": project, "kind": "build"}, pluck="canonical",
			order_by="seq desc", limit=1)
		if not last or json.loads(last[0])["body"].get("fingerprint") != now:
			log.append_event(project, "build", body={"fingerprint": now, "versions": describe.versions()})


def _verify() -> None:
	from construction_core.approvals import verify

	verify.run(job=True)


def _retention() -> None:
	from construction_core.approvals import retention

	retention.run()


def _digest() -> None:
	mailbox = frappe.db.get_single_value(api.SETTINGS, "evidence_mailbox", cache=False)
	if not mailbox:
		frappe.logger("construction_core").info("approvals digest skipped: no evidence mailbox is set")
		return
	now, top = log._now().replace(tzinfo=None), heads()
	lines = frappe.get_all(log.EVENT, filters={"at_utc": (">=", now - DAY)}, fields=["project", "seq", "canonical"],
		order_by="project asc, seq asc")  # shortcut: the day's lines are all in the body; attach them if a day runs large
	body = [f"<p>{escape(_('Approvals chain heads on {0} (UTC)').format(f'{now:%d %b %Y}'))}</p>"]
	for project, h in top.items():
		mine = [x.canonical for x in lines if x.project == project]
		body.append(f"<h3>{escape(project)}</h3><p>{escape(_('Position {0}').format(h['seq']))}<br>{h['hash']}</p>"
			f"<p>{escape(_('{0} events in the last 24 hours').format(len(mine)))}</p>"
			+ (f"<pre>{escape(chr(10).join(mine))}</pre>" if mine else ""))
	files = [{"fname": "heads.json", "fcontent": json.dumps([{"project": p, **h} for p, h in top.items()]).encode()}]
	try:
		sent = receipts._deliver([mailbox], _("Approvals daily digest {0}").format(f"{now:%Y-%m-%d}"), "".join(body), files)
	except Exception:
		frappe.log_error(title="construction_core: the approvals daily digest could not be sent")
		return
	for project, h in top.items():
		log.append_event(project, "anchor", body={"heads": [{"project": project, **h}], "recipients": [mailbox], "message_id": sent["message_id"]})


def _approver_heads() -> None:
	since = log._now().replace(tzinfo=None) - DAY
	for project, h in heads().items():
		# a request in internal review sends the client no email (§14.3): its events never count
		if not frappe.db.sql("""select 1 from `tabApproval Event` e where e.project = %s and e.at_utc >= %s
				and e.kind not in %s and not exists (select 1 from `tabApproval Event` i where i.request = e.request
				and i.kind = 'internal_review') limit 1""", (project, since, (*log.SYSTEM_EVENTS, *log.INTERNAL_EVENTS))):
			continue
		name = frappe.db.get_value(api.PROJECT, project, "project_name") or project
		html = f"<p>{escape(_('Chain head of {0}').format(name))}</p><p>{escape(_('Position {0}').format(h['seq']))}<br>{h['hash']}</p>"
		for user, confirmed in api.approvers(project).items():
			if not confirmed:
				continue
			try:
				receipts._deliver([api._email(user)], _("Chain head of {0}").format(name), html, [])
			except Exception:
				frappe.log_error(title="construction_core: an approver's chain head could not be sent")
