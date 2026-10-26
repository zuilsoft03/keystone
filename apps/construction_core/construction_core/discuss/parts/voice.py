"""The voice part (design §3.6; P3-67; D-364): a voice note, sent on its own, with an optional short caption (L-13).

**Why a part.** A voice message has its own kind (``Voice``, before ``Files`` in KIND_ORDER) and its own card and
player on the screen, so it is its own part key (§13.6 item 3). Its bytes are an attachment like any other: staged by
``attachments.upload`` with ``voice=1`` through the one pipeline (discuss.media: type, signature, size, structure,
ClamAV), stored as a Discuss Attachment of kind ``voice``, made a File in the conversation's folder at the send. The
row also holds what the server read from the container (length, type, codec; ``audio``) and the waveform, so the card
comes from the attachments part's one read of the page: a voice card adds no query.

**Send.** ``parts: {"voice": {"attachment": id, "waveform": [...]}}``. ``claim`` locks the row and accepts only the
sender's own waiting voice note in this thread, with WAVE_MIN to WAVE_MAX whole numbers from 0 to WAVE_TOP; any other
key (a length, a type) is refused, since the server states those itself. A voice note goes with no file part.

**Who sends.** Staff, and clients with the same checks and limits (D-364), wherever a file may be sent (attachments'
rules, including the portal's Files switch for a client). Partners join after go-live (D-444).

**Serving.** The card's ``url`` is the File's private address; the File's name carries the extension read from the
bytes (``.m4a``, ``.ogg``, ``.weba``), so the existing private file path answers ``audio/mp4``, ``audio/ogg`` or
``audio/webm`` (SEC-16) with Range support and nosniff (P3-67's measurement). Its browser cache rule is Q-105's (P3-10).
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from construction_core import audio
from construction_core.discuss import media
from construction_core.discuss.parts import attachments
from construction_core.discuss.registry import Part, SendCtx, ViewCtx
from construction_core.permissions import client_section_open

WAVE_MIN, WAVE_MAX, WAVE_TOP = 50, 128, 100  # "about 100 values" (§3.6): the recorder sends 100, each 0..100
KEYS = {"attachment", "waveform"}
NOT_WAITING = "A voice note is no longer waiting to be sent. Record it again."


# --- the upload -----------------------------------------------------------------------------------------------------


def incoming(part) -> tuple[str, str, bytes]:
	"""(display name, extension, bytes) of an uploaded recording: the sender's file name is not used; the extension is
	read from the bytes, so the stored File is served with the detected audio type."""
	content = part.stream.read(audio.MAX_BYTES + 1)
	ext = audio.sniff(content)
	if not ext:
		frappe.throw(_("This recording could not be read. Record it again."))
	return f"Voice note {now_datetime():%Y-%m-%d %H.%M}.{ext}", ext, content


# --- the send -------------------------------------------------------------------------------------------------------


def claim(ctx: SendCtx, value) -> dict:
	"""The sender's waiting voice note and a checked waveform; no writes."""
	if not isinstance(value, dict) or set(value) - KEYS or not isinstance(value.get("attachment"), str):
		frappe.throw(_("The voice note is not valid"))
	sending = frappe.flags.get("cc_discuss_write")  # send.CLAIM: the whole send this part is claimed in
	if sending and "attachments" in (sending.parts or {}):
		frappe.throw(_("Send a voice note on its own."))
	wave = waveform(value.get("waveform"))
	if ctx.sender == "client" and not client_section_open("File", ctx.thread.project):
		frappe.throw(_("Sending files is switched off for this project"), frappe.PermissionError)
	name = value["attachment"]
	r = attachments.locked([name]).get(name)
	if (not r or r.kind != "voice" or r.uploader != ctx.author or r.thread != ctx.thread.name or r.state != "Pending"
			or media.expired(r) or r.checking or r.scan_reason):
		frappe.throw(_(NOT_WAITING), frappe.PermissionError)
	return {"attachment": name, "waveform": wave}


def waveform(value) -> list[int]:
	if (not isinstance(value, list) or not WAVE_MIN <= len(value) <= WAVE_MAX
			or not all(type(v) is int and 0 <= v <= WAVE_TOP for v in value)):  # type(): True is not a level
		frappe.throw(_("The voice note's waveform is not valid"))
	return value


def write(doc, value: dict) -> None:
	"""The note's File is made like any sent file's (attachments.write), then its waveform is kept on the row."""
	attachments.write(doc, [value["attachment"]])
	frappe.db.set_value(media.DOCTYPE, value["attachment"], "voice_wave",
		json.dumps(value["waveform"], separators=(",", ":")), update_modified=False)


# --- the card -------------------------------------------------------------------------------------------------------


def build(ctx: ViewCtx, rows: list) -> dict:
	"""{message: card} from the attachments part's read of the page (no query of its own)."""
	got = attachments.page(ctx, rows)
	if not got:
		return {}
	return {a.message: card(a, got.files[a.file]) for a in got.attached if a.kind == "voice" and a.file in got.files}


def card(a, f) -> dict:
	"""The player's facts: the private address, the served type, the server's length, the waveform. No File id."""
	return {"_ref": ("File", f.name), "attachment": a.name, "url": f.file_url, "type": a.voice_type,
		"codec": a.voice_codec, "length": float(a.voice_length or 0), "waveform": _wave(a.voice_wave),
		"size": cint(a.file_size or f.file_size), "sent_on": str(a.sent_on) if a.sent_on else None}


def _wave(raw) -> list:
	try:
		value = json.loads(raw) if raw else []
	except ValueError:
		return []
	return value if isinstance(value, list) else []


def capable(ctx: ViewCtx, thread) -> bool:
	"""The mic shows where a file may be sent (attachments.capable: the thread row and one memo per project)."""
	return attachments.capable(ctx, thread)


PART = Part(key="voice", audiences=frozenset({"Internal", "Client"}), senders=frozenset({"staff", "client"}),
	implies_kind="Voice", claim=claim, build=build, capable=capable, write=write)
