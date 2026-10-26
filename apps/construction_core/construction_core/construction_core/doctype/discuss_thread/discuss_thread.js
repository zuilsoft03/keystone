// Copyright (c) 2026, Construction Workspace and contributors
// For license information, please see license.txt

// P3-64 (R-32 §14.7): an old Desk link to a conversation (/app/discuss-thread/<name>) opens it in the workspace's
// Discussion, which resolves a thread to its room with the thread beside it. Rooms and threads are read and written there.
// A System Manager may stay on the Desk form with ?desk=1 (audit F7), and gets a button to open it in the workspace.
frappe.ui.form.on("Discuss Thread", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.project) return;
		const target = `/workspace/${encodeURIComponent(frm.doc.project)}/discuss/${encodeURIComponent(frm.doc.name)}`;
		const stay = new URLSearchParams(window.location.search).get("desk") === "1" && frappe.user.has_role("System Manager");
		if (!stay) {
			window.location.replace(target);
			return;
		}
		frm.add_custom_button(__("Open in the workspace"), () => (window.location.href = target));
	},
});
