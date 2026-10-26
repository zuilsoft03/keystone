"""Office files through the Document Server's conversion API (P3-75, design §15.2, gate G1; research §3.4).

The Document Server (already isolated on the internal ``office`` network, D-082) converts the first page, slide or
sheet to a PNG of at most 400 px. It fetches the file by the same signed, short-lived link the editor uses
(``office.api.fetch``) and is asked under a key of its own, ``thumb-<sha256>-<spec>-<renderer version>``, never the
editor's document key. Its PNG is fetched from its cache over the internal network only, then drawn again in the
renderer like any other picture: the converter's bytes are never stored as given.

The JWT shape is the spike's (``phase0/sandbox/scripts/A_convert.py``), which 9.4.0.1 accepts: the parameters signed in
the body's ``token`` and, wrapped as ``{"payload": ...}``, in the ``AuthorizationJwt`` header. A site with no Document
Server (the ``core`` profile) shows the placeholder.
"""

import time

import frappe
import requests

from construction_core.previews import PX, RENDERER_VERSION, SPEC

TIMEOUT = 120  # seconds for one synchronous conversion (the spike measured about 1 s for an ordinary document)
FIXED = {-3: "failed", -5: "locked", -7: "failed", -9: "failed", -10: "too_large"}  # documented error codes
PNG = b"\x89PNG\r\n\x1a\n"


class Refusal(Exception):
	"""The Document Server answered for good: no preview of these bytes (a password, too large, unreadable)."""

	def __init__(self, reason: str):
		super().__init__(reason)
		self.reason = reason


class Unavailable(Exception):
	"""The Document Server could not answer now: try again later."""


def configured() -> bool:
	return bool(frappe.conf.get("cc_office_jwt_secret"))


def convert(file: str, ext: str, sha256: str) -> bytes:
	"""The PNG of a File's first page. Raises Refusal or Unavailable."""
	from construction_core.office import api as office

	exp = int(time.time()) + office.LINK_TTL
	url = (f"{office._internal_site()}/api/method/construction_core.office.api.fetch?file={file}&exp={exp}"
		f"&sig={office._sig('fetch', file, exp)}")
	params = {"async": False, "filetype": ext, "key": f"thumb-{sha256[:40]}-{SPEC}-{RENDERER_VERSION}",
		"outputtype": "png", "title": f"preview.{ext}", "url": url,
		"thumbnail": {"aspect": 1, "first": True, "width": PX, "height": PX}}
	server = (frappe.conf.get("cc_office_internal_ds") or "http://documentserver").rstrip("/")
	try:
		r = requests.post(f"{server}/converter", json={**params, "token": office.jwt_encode(params)}, timeout=TIMEOUT,
			headers={"Accept": "application/json", office.JWT_HEADER: f"Bearer {office.jwt_encode({'payload': params})}"},
			allow_redirects=False)
		answer = r.json() if r.status_code == 200 else {}
	except (requests.RequestException, ValueError) as e:
		raise Unavailable(type(e).__name__) from None
	return _result(answer, office)


def _result(answer: dict, office) -> bytes:
	error = answer.get("error") if isinstance(answer, dict) else None
	if error is not None:
		if int(error) in FIXED:
			raise Refusal(FIXED[int(error)])
		raise Unavailable(f"error {error}")  # unknown, timeout, download, database, token: a passing failure
	if not answer.get("endConvert") or not answer.get("fileUrl"):
		raise Unavailable("not finished")
	try:
		content = office._download_from_ds(answer["fileUrl"])
	except (requests.RequestException, frappe.ValidationError):
		frappe.clear_last_message()
		raise Unavailable("download") from None
	if not content.startswith(PNG):
		raise Refusal("failed")
	return content
