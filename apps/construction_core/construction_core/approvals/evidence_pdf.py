"""The evidence PDF of an answered request (design §3.6, §4.6; P3-81).

- ``make(request)``: the chained PDF. It holds the terms shown, the locked line, the frozen files' names and SHA-256,
  the answer, the decider's name, the time, the chain position and the request's events, and no personal block (no
  network address, device, location or signature picture). The bytes are stored once (``frozen.store``) and an
  ``evidence_pdf`` event names their SHA-256 and the answer it covers. WeasyPrint's output differs per run, so nothing
  ever renders it again to verify: ``verify`` checks the stored bytes.
- ``render(request, personal=True)``: the same with the personal page, for Construction and System Managers only. It is
  never stored and never chained.
- Offline: WeasyPrint may fetch ``data:`` URIs only (``_fetch``), so a crafted title cannot make the server read a file
  or a URL. Fonts are the system's (DejaVu Sans in the image).
"""

import base64
import json

import frappe
from frappe import _
from frappe.utils import get_fullname

from construction_core.approvals import agreement, api, frozen, log, receipts
from construction_core.approvals.answer import signature_picture

TEMPLATE = "templates/approval_evidence.html"
MANAGERS = {"Construction Manager", "System Manager"}


def _fetch(url, *args, **kwargs):
	from weasyprint import default_url_fetcher

	if not url.startswith("data:"):
		raise ValueError(f"offline: {url.split(':', 1)[0]} URLs are refused")
	return default_url_fetcher(url, *args, **kwargs)


def _answer(request: str):
	e = receipts.answer_of(request)
	if not e:
		frappe.throw(_("This request has no answer yet"))
	return e


def html(request: str, personal: bool = False) -> str:
	"""The page's HTML: the chained part, plus the personal page when ``personal``."""
	r, e = frappe.get_doc(log.REQUEST, request), _answer(request)
	terms, body = json.loads(r.snapshot)["terms"], json.loads(e.canonical)["body"]
	option = next((o for o in terms.get("options") or [] if o["key"] == body.get("option")), None)
	files = [{"name": f["name"], "sha256": f["shown_sha256"]} for f in json.loads(r.frozen_files or "{}").values()]
	events = [{"kind": x.kind, "seq": x.seq, "at": f"{x.at_utc}Z", "who": get_fullname(x.actor)} for x in
		frappe.get_all(log.EVENT, filters={"request": request}, fields=["kind", "seq", "at_utc", "actor"], order_by="seq asc")]
	ctx = {"title": r.subject_title or terms.get("title") or "", "reference": terms.get("number") or r.subject_name,
		"project": frappe.db.get_value(api.PROJECT, r.project, "project_name"),
		"terms": [(k, str(v)) for k, v in terms.items() if k in ("revision", "currency", "total", "days") and v],
		"options": terms.get("options") or [], "line": agreement.lines(r).get(body.get("option") or "record", ""),
		"files": files, "answer": e.kind, "option": option and option["label"], "reason": body.get("reason") or "",
		"decider": get_fullname(receipts.decider_of(e)), "when": receipts.when(e.at_utc), "utc": f"{e.at_utc}Z",
		"seq": e.seq, "hash": e.hash, "events": events, "personal": None}
	if personal:
		d = frappe.db.get_value(log.DETAIL, {"event": e.name}, list(log.DETAIL_FIELDS), as_dict=True) or {}
		sealed = (body.get("signature") or {}).get("file")
		picture = signature_picture(sealed) if sealed else None
		ctx["personal"] = {**{k: d.get(k) or "" for k in log.DETAIL_FIELDS if k != "location"},
			"location": json.loads(d["location"]) if d.get("location") else None,
			"signature": picture and "data:image/png;base64," + base64.b64encode(picture).decode()}
	return frappe.render_template(TEMPLATE, ctx)


def render(request: str, personal: bool = False) -> bytes:
	from weasyprint import HTML

	if personal and not MANAGERS & set(frappe.get_roles()):
		frappe.throw(_("Only managers may see the personal page"), frappe.PermissionError)
	return HTML(string=html(request, personal), url_fetcher=_fetch).write_pdf()


def make(request: str) -> str:
	"""The chained PDF of the request's latest answer, stored, with its ``evidence_pdf`` event (its name). A request
	that already has one for that answer gets the existing event back."""
	e = _answer(request)
	for name, text in frappe.get_all(log.EVENT, filters={"request": request, "kind": "evidence_pdf"},
			fields=["name", "canonical"], order_by="seq desc", as_list=True):
		if json.loads(text)["body"].get("answer") == e.name:
			return name
	sha = frozen.store(render(request))
	return log.append_event(frappe.db.get_value(log.REQUEST, request, "project"), "evidence_pdf", request=request,
		body={"file": sha, "sha256": sha, "answer": e.name})
