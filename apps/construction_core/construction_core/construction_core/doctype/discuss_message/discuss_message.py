# Copyright (c) 2026, Construction Workspace and contributors
"""Discuss Message: append-only, so a message is its own snapshot (D-034).

- Every insert runs the core checks (discuss.checks): the thread is read as the author, project and audience come
  from it, Locked, audience, staff-only, length, client_id, the attachment and mentions. So a staff REST insert and
  the provider path are checked as our endpoints are (rule 5).
- A client has no create (D-387): a client insert is accepted only under the claim that discuss.send sets, matched to
  this thread, author and client_id, and consumed once.
- Each insert counts against its author's rate limit (D-411, D-412): a REST insert too; a retried send that returns
  its first message is never inserted, so never counted.
- The server owns kind, author, project, audience, the pin fields and P3-68's edited, removed, reactions and Agreed
  fields: they are reset here whatever the caller sent. Only discuss.edit and discuss.actions change a sent row, with
  db_set (D-388); track_changes is off, so no Frappe Version row keeps an earlier or removed text (D-410).
  The kind comes from what the message carries (KIND_ORDER); System only under the server's own flag (D-419), which
  names the author and fixes the text. A System message is never rate-counted and tells no one by a notice; the
  migration's cards hold back their live events and counters too (§14.3).
- A staff-only note (D-098) lives inside a client conversation for the team only: clients never read it, it never
  reaches them by realtime (discuss.live), and it does not move the thread's public counters.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from construction_core.core.events import emit
from construction_core.discuss import checks, live, rooms, send
from construction_core.permissions import _bypass, is_client


class DiscussMessage(Document):
	def before_insert(self):
		system = send.take_system(self)
		thread = checks.system(self, system) if system else checks.run(self)
		claim = None if system else send.take_claim(self)
		if not (claim or system) and is_client(self.author):
			frappe.throw(_("Clients post through the portal"), frappe.PermissionError)
		if not (system or (claim and claim.uncounted)):
			# Counted before the parts' claims (P3-66 audit S1): a send a claim refuses counts too, so tags and mentions
			# cannot be tried without limit.
			send.rate_limit(self.author)
		self.kind = "System" if system else send.claim_parts(self, thread, claim)
		if not system:
			settle_tokens(self)  # P3-66: @[u:n] and #[r:n] name only what the claims kept
		if self.kind == "Text" and not self.content:
			frappe.throw(_("Write a message first"))
		self.pinned, self.pinned_by, self.pinned_on = 0, None, None
		# P3-68: the edit, remove, reaction and Agreed endpoints own these; an insert never sets them (rule 5)
		self.edited, self.removed, self.reactions = 0, 0, None
		self.agreed, self.agreed_by, self.agreed_on = 0, None, None
		self.flags.cc_quiet = bool(system and system.quiet)

	def validate(self):
		if not self.is_new() and not _bypass(frappe.session.user):
			frappe.throw(_("Messages cannot be edited: post a new message instead"), title=_("Append-only"))

	def on_trash(self):
		if not _bypass(frappe.session.user):
			frappe.throw(_("Messages cannot be deleted"), frappe.PermissionError)

	def before_rename(self, old, new, merge=False):
		"""A message a pointer or an anchor names keeps its name: they name it as Data (D-418)."""
		if (frappe.db.exists("Discuss Pointer", {"target_type": "Discuss Message", "target_name": old})
				or frappe.db.exists("Discuss Anchor", {"message_id": old})):
			frappe.throw(_("A message keeps its name"), frappe.PermissionError)

	def after_insert(self):
		if self.flags.cc_quiet:
			return  # a migrated card: the patch runs the counters once per room (§14.3)
		send.write_parts(self)  # P3-65: the parts' own rows, before anyone is told of the message
		if not self.staff_only:  # a staff-only note moves no counter a client reads
			send.queue_counters(self.thread, self.name)
		if self.kind != "System":  # a card or a mirror: what it points at has told its people already
			from construction_core.notifications import on_message

			on_message(self)  # P3-06: staff get a bell notice, never the message; a mentioned client gets an email link
			rooms.follow_message(self)  # after the commit (§14.5)
		live.message_event(self)
		emit("discuss.message_posted", self)


def settle_tokens(doc) -> None:
	"""The mention and tag tokens of the text (design §3.4, §3.5): a token names a slot its part's claim kept, or the
	send is refused; a REST insert has no claim, so its text carries no token."""
	from construction_core.discuss.parts import mentions, refs

	mentions.settle(doc)
	refs.settle(doc)


def on_doctype_update():
	"""Paging reads (thread, creation, name); a retried send finds its first message by (author, client_id) (F8)."""
	frappe.db.add_index("Discuss Message", ["thread", "creation", "name"], "thread_creation_name")
	frappe.db.add_unique("Discuss Message", ["author", "client_id"], constraint_name="unique_author_client_id")
