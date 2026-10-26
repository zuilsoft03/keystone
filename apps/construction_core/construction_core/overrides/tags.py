"""Overrides of Desk's whitelisted tag and like calls (P3-76 round 5, D2). Each writes a record's _user_tags or
_liked_by with frappe.db.set_value and no Document hook, and a client reads both columns on a request: toggle_like
checks read only and writes _liked_by on an unlike, remove_tag checks nothing before it writes, add_tag and add_tags
write before their Tag Link. Each refuses a ledger doctype, by the name the database matches (D4), and otherwise calls
Frappe's own with the stored name and the same arguments.
"""

import frappe
from frappe.desk import like
from frappe.desk.doctype.tag import tag as frappe_tag

from construction_core.approvals.log import not_ledger


@frappe.whitelist()
def toggle_like(doctype: str, name: str, add: str | bool = False):
	return like.toggle_like(not_ledger(doctype), name, add)


@frappe.whitelist()
def add_tag(tag: str, dt: str, dn: str, color: str | None = None):
	return frappe_tag.add_tag(tag, not_ledger(dt), dn, color)


@frappe.whitelist()
def add_tags(tags: str | list[str], dt: str, docs: str | list[str], color: str | None = None):
	return frappe_tag.add_tags(tags, not_ledger(dt), docs, color)


@frappe.whitelist()
def remove_tag(tag: str, dt: str, dn: str):
	return frappe_tag.remove_tag(tag, not_ledger(dt), dn)
