"""P3-63 (F7): one Discuss Read State per (thread, user). Two first reads at once could make two rows, so this keeps
each pair's latest row, deletes the others, and adds the unique key. It runs before the model sync, where
DiscussReadState's on_doctype_update would otherwise meet the duplicates."""

import frappe


def execute():
	if not frappe.db.table_exists("Discuss Read State"):
		return
	pairs = frappe.db.sql("""select thread, user from `tabDiscuss Read State`
		group by thread, user having count(*) > 1""", as_dict=True)
	for p in pairs:
		rows = frappe.db.sql("""select name from `tabDiscuss Read State` where thread = %s and user = %s
			order by ifnull(last_read_on, '1900-01-01') desc, modified desc, name""", (p.thread, p.user), pluck=True)
		frappe.db.delete("Discuss Read State", {"name": ["in", rows[1:]]})
	frappe.db.add_unique("Discuss Read State", ["thread", "user"], constraint_name="unique_thread_user")
