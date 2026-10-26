"""The canonical text and the hashes of the approvals ledger (design §4.2, D-428).

- ``text(data, places)``: ``json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`` on NFC text, with a
  ``canonical_version`` key. Every value comes out a string: an int as its digits, a Decimal quantized to ``places``
  (stored in the text as ``places``), a datetime as UTC with microseconds and Z (a naive one is the site's local time,
  as Frappe stores it), a date as YYYY-MM-DD. A float, a bool or None is refused: the caller says what it means.
- A list of rows (dicts with ``idx``) is ordered by ``idx``, which then leaves the row; any other list keeps its order.
- Frappe's own columns (``owner``, ``modified_by``, ``creation`` …) are refused: a User rename rewrites them in every
  table. HTML is made plain text by the caller, with ``plain``, which keeps cell bounds, link targets and picture sources.
- ``link(prev, text)`` = SHA-256(prev_hex + "\\n" + text); ``genesis(site, project)`` is a project's first previous hash,
  from a constant label, never from a row (seq 1's text holds the site, so it is rebuilt from the chain alone).
"""

import hashlib
import html
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import frappe

VERSION = "1"
GENESIS_LABEL = "Keystone approvals chain, version 1"
FRAPPE_COLUMNS = frozenset({"owner", "modified_by", "creation", "modified", "docstatus", "idx", "parent", "parenttype",
	"parentfield", "doctype", "_user_tags", "_comments", "_assign", "_liked_by", "_seen"})
RESERVED = frozenset({"canonical_version", "places"})
HEX64 = re.compile(r"^[0-9a-f]{64}$")
_BLOCK = re.compile(r"<\s*(?:br|hr|/p|/div|/li|/tr|/h[1-6]|/blockquote|/pre)\b[^>]*>", re.IGNORECASE)
_CELL = re.compile(r"<\s*/\s*t[dh]\b[^>]*>", re.IGNORECASE)
_ATTR = r"""\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""
_LINK = re.compile(rf"<a\b[^>]*?\bhref{_ATTR}[^>]*>(.*?)<\s*/\s*a\s*>", re.IGNORECASE | re.DOTALL)
_IMAGE = re.compile(rf"<img\b[^>]*?\bsrc{_ATTR}[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]*>")


def text(data: dict, places: int | None = None) -> str:
	"""The canonical text of ``data``, exactly as it is hashed and stored."""
	if not isinstance(data, dict):
		raise TypeError("canonical text is made from a dict")
	if places is not None and (isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 9):
		raise ValueError("places is a whole number from 0 to 9")
	body = _value(data, places)
	if RESERVED & set(body):
		raise ValueError("canonical_version and places are set here")
	out = {"canonical_version": VERSION, **body}
	if places is not None:
		out["places"] = str(places)
	return json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: str | bytes) -> str:
	return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def link(prev: str, canonical_text: str) -> str:
	"""One link of the chain: SHA-256(prev_hex + "\\n" + canonical_utf8)."""
	if not isinstance(prev, str) or not HEX64.match(prev):
		raise ValueError("the previous hash is 64 lowercase hex characters")
	return sha256(f"{prev}\n{canonical_text}")


def genesis(site: str, project: str) -> str:
	return sha256(f"{GENESIS_LABEL}\n{site}\n{project}")


def plain(value: str | None) -> str:
	"""An HTML field as plain text: block ends become line breaks, a cell's end " | ", a link "text (href)", a picture
	"[image: src]"; the other tags go, entities are read, spaces are collapsed."""
	s = _LINK.sub(lambda m: f"{m[4]} ({m[1] or m[2] or m[3] or ''})", value or "")
	s = _IMAGE.sub(lambda m: f"[image: {m[1] or m[2] or m[3] or ''}]", s)
	s = html.unescape(_TAG.sub("", _BLOCK.sub("\n", _CELL.sub(" | ", s))))
	lines = (" ".join(line.split()) for line in s.splitlines())
	return unicodedata.normalize("NFC", "\n".join(line for line in lines if line))


def _value(v, places):
	if isinstance(v, bool) or v is None or isinstance(v, float):
		raise TypeError(f"canonical values are strings, ints, Decimals, dates, dicts and lists, not {type(v).__name__}")
	if isinstance(v, str):
		return unicodedata.normalize("NFC", v)
	if isinstance(v, int):
		return str(v)
	if isinstance(v, Decimal):
		return _amount(v, places)
	if isinstance(v, datetime):
		aware = v if v.tzinfo else v.replace(tzinfo=ZoneInfo(frappe.utils.get_system_timezone()))
		return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
	if isinstance(v, date):
		return v.isoformat()
	if isinstance(v, dict):
		out = {}
		for key, item in v.items():
			if not isinstance(key, str):
				raise TypeError("canonical keys are strings")
			key = unicodedata.normalize("NFC", key)
			if key in FRAPPE_COLUMNS:
				raise ValueError(f"{key} is a Frappe column and is never in the canonical text")
			if key in out:
				raise ValueError(f"two keys read {key} once normalized")
			out[key] = _value(item, places)
		return out
	if isinstance(v, list | tuple):
		return [_value(item, places) for item in _by_idx(v)]
	raise TypeError(f"{type(v).__name__} has no canonical form")


def _by_idx(items) -> list:
	"""Rows in ``idx`` order, without ``idx``; a list with no rows keeps its order."""
	rows = [isinstance(i, dict) and "idx" in i for i in items]
	if not any(rows):
		return list(items)
	if not all(rows):
		raise ValueError("a list mixes rows with idx and items without")
	order = [int(i["idx"]) for i in items]
	if len(set(order)) != len(order):
		raise ValueError("two rows share an idx")
	return [{k: x for k, x in i.items() if k != "idx"} for _n, i in sorted(zip(order, items), key=lambda p: p[0])]


def _amount(v: Decimal, places) -> str:
	if places is None:
		raise ValueError("an amount needs the snapshot's places")
	if not v.is_finite():
		raise ValueError("an amount is a finite number")
	q = v.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
	return format(abs(q) if q == 0 else q, "f")  # never "-0.00" or an exponent
