"""ChatProvider (D-080, DR-9): threads anchored to records, with an audience.

The v1 provider is our own Discuss threads (P1-12). ``NullChat`` is the provider-neutral null implementation:
it runs as real code (D-063) and is what core uses when no chat is configured. An optional adapter such as
``ws_raven`` would only add a channel; it never holds the record of truth.
"""

from __future__ import annotations

import frappe

AUDIENCES = ("Internal", "Client")


class ChatProvider:
	name = "abstract"

	def ensure_thread(self, anchor_doctype: str, anchor_name: str, audience: str = "Internal") -> str:
		raise NotImplementedError

	def post(self, thread_id: str, text: str) -> str:
		raise NotImplementedError


class NullChat(ChatProvider):
	"""Accepts and validates calls, stores nothing, returns stable ids. Used when no chat is configured."""

	name = "null"

	def ensure_thread(self, anchor_doctype, anchor_name, audience="Internal"):
		if audience not in AUDIENCES:
			frappe.throw(f"Unknown audience {audience}")
		frappe.get_doc(anchor_doctype, anchor_name).check_permission("read")
		return f"null:{anchor_doctype}:{anchor_name}:{audience}"

	def post(self, thread_id, text):
		if not thread_id.startswith("null:"):
			frappe.throw("Not a NullChat thread")
		return f"{thread_id}:{frappe.generate_hash(length=10)}"


def get_chat() -> ChatProvider:
	path = frappe.conf.get("cc_chat_provider")
	if path:
		return frappe.get_attr(path)()
	try:
		from construction_core.discuss.provider import DiscussChat  # P1-12; core module, not an adapter

		return DiscussChat()
	except ImportError:
		return NullChat()
