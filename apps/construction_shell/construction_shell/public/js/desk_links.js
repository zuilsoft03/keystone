// P2-05, P2-07 (D-120): Desk forms of the tools open them in the workspace. Added by the shell (hooks.doctype_js), because
// construction_core never refers to the shell. The core's Desk tool pages are retired (P2-07).
(function () {
	const OFFICE = /\.(docx|doc|odt|rtf|txt|docm|dotx|xlsx|xls|ods|csv|pptx|ppt|odp)$/i;
	const go = (project, section, item, action) => {
		const parts = [project, section, item, action].filter(Boolean).map(encodeURIComponent);
		window.location.href = "/workspace/" + parts.join("/");
	};

	frappe.ui.form.on("Whiteboard", {
		refresh(frm) {
			if (!frm.is_new() && frm.doc.project) {
				frm.add_custom_button(__("Open in workspace"), () => go(frm.doc.project, "whiteboards", frm.doc.name));
			}
		},
	});

	frappe.ui.form.on("CAD Drawing", {
		refresh(frm) {
			if (!frm.is_new() && frm.doc.project) {
				frm.add_custom_button(__("Open in workspace"), () => go(frm.doc.project, "takeoff", frm.doc.name));
			}
		},
	});

	frappe.ui.form.on("Project Document", {
		refresh(frm) {
			if (!frm.doc.document_file || !frm.doc.project) return;
			frappe.db.get_value("File", frm.doc.document_file, "file_name").then((r) => {
				if (r.message && OFFICE.test(r.message.file_name || "")) {
					frm.add_custom_button(__("Edit file in workspace"), () => go(frm.doc.project, "files", frm.doc.document_file, "edit"));
				}
			});
		},
	});

	frappe.ui.form.on("File", {
		refresh(frm) {
			if (!frm.is_new() && !frm.doc.is_folder && frm.doc.cc_project && OFFICE.test(frm.doc.file_name || "")) {
				frm.add_custom_button(__("Edit in workspace"), () => go(frm.doc.cc_project, "files", frm.doc.name, "edit"));
			}
		},
	});
})();
