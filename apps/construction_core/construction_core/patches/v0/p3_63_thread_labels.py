"""P3-63 (F11, D-370): a thread on a record stores a neutral label, the record's type and number, never the record's
own title. Canvas threads stored "Board <board title>", which a client kept after the board was unshared. Project
threads keep their author's text."""

import frappe

from construction_core.discuss.provider import label


def execute():
	rows = frappe.get_all("Discuss Thread", filters={"anchor_doctype": ["!=", "Construction Project"]},
		fields=["name", "title", "anchor_doctype", "anchor_name"])
	for r in rows:
		neutral = label(r.anchor_doctype, r.anchor_name)
		if r.title != neutral:
			frappe.db.set_value("Discuss Thread", r.name, "title", neutral, update_modified=False)
