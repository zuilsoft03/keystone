"""The chat's extension core (D-358, design §13.1 S1): what a payload part is, and the contexts the core hands it.

A part is one key under ``message['parts']``. Its module (``discuss/parts/<key>.py``) declares where it may appear and
who may send it, validates what a sender claims, and builds what a viewer sees, batched per page. The core keeps every
guarantee around it: the checks run first, an undeclared audience or sender is refused before the claim, the core
derives the kind, build only ever receives rows the viewer may read, and the response exit strips internal ids.
Registries are static tuples (rule 14): no hooks, no loader.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import frappe

from construction_core.permissions import is_client

KINDS = ("Text", "Files", "Voice", "Poll", "System")  # Discuss Message.kind, a closed Select (plan §3.1)
KIND_ORDER = ("Poll", "Voice", "Files")  # the first one a message carries wins; else Text. System: server flag only
SENDERS = ("staff", "client")  # 'partner' joins with P3-32 (D-409)
# A System message's stored text: one fixed neutral word, never a title or copied text (rule 2, D-419). Its part draws
# the card at read time; the legacy adapters show this word until P3-64.
SYSTEM_TEXT = "Conversation"


@dataclass(frozen=True)
class SendCtx:
	"""What a part's claim may read: the thread row, the author and how they send. Never a request value."""

	thread: Any
	author: str
	sender: str
	staff_only: bool


@dataclass(frozen=True)
class ViewCtx:
	"""Who reads: the session user, or the client a staff preview shows (portal_preview.client_of). ``memo`` holds
	this read's answers, such as (doctype, name, user) -> may read, so one page asks once per record."""

	user: str
	thread: Any
	staff: bool
	memo: dict = field(default_factory=dict, compare=False)

	def can_read(self, doctype: str, name: str, user: str | None = None) -> bool:
		user = user or self.user
		key = (doctype, name, user)
		if key not in self.memo:
			self.memo[key] = bool(frappe.has_permission(doctype, "read", doc=name, user=user, throw=False))
		return self.memo[key]

	def readable(self, doctype: str, names, fields=("name",)) -> list:
		"""The rows of ``names`` the viewer reads, in one get_list as the viewer: the list form of the same predicate
		(project_scoped is can_access's SQL side, D-086). Each answer goes into ``memo``, so can_read and respond's
		``_ref`` check ask nothing more for this page."""
		names = [n for n in dict.fromkeys(names) if n]
		if not names:
			return []
		rows = frappe.get_list(doctype, filters={"name": ["in", names]}, fields=list(fields), limit=len(names),
			user=self.user)
		found = {r.name for r in rows}
		for n in names:
			self.memo[(doctype, n, self.user)] = n in found
		return rows


@dataclass(frozen=True)
class Part:
	key: str  # under message['parts']; never reused; shape changes are additive only
	audiences: frozenset  # thread audiences it may appear in
	senders: frozenset  # who may claim it: 'staff' | 'client'
	implies_kind: str | None  # 'Files' | 'Voice' | 'Poll'; never 'System'
	claim: Callable[[SendCtx, Any], Any] | None  # validate and normalise; no writes; may only refuse
	build: Callable[[ViewCtx, list], dict]  # {message: value}; an item naming a record or file has '_ref'
	capable: Callable[[ViewCtx, Any], bool] | None  # whether the viewer's composer offers it in this thread
	# After the message insert, under the same claim: the part's own rows (P3-65, §13.3). (message doc, claimed value).
	write: Callable[[Any, Any], None] | None = None


def sender_of(user: str) -> str:
	"""The account kind, from the session. "Team" means not a client until P3-27's is_staff (D-409)."""
	return "client" if is_client(user) else "staff"


def derive_kind(kinds) -> str:
	return next((k for k in KIND_ORDER if k in kinds), "Text")
