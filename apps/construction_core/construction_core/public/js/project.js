// Project form (P1-14, D-098): invite client contacts (one login each, e.g. a couple) and open the client chat.
// P3-16 (D-209): an invitation link, shown once with a QR, and mailed when an email is given.
frappe.ui.form.on("Construction Project", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Invite a client"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Invite a client"),
				fields: [
					{ fieldname: "full_name", fieldtype: "Data", label: __("Name") },
					{ fieldname: "email", fieldtype: "Data", options: "Email", label: __("Email (if you know it)"),
						description: __("With an email, the client can start at once. Without one, share the link by chat or QR; you confirm each person.") },
					{ fieldname: "job_title", fieldtype: "Data", label: __("Job title on this project"), description: __("Seen by the project team only") },
				],
				primary_action_label: __("Create invitation"),
				primary_action(values) {
					frappe
						.call({
							method: "construction_core.onboarding.invites.create_invite",
							type: "POST",
							args: { project: frm.doc.name, email: values.email, full_name: values.full_name, job_title: values.job_title },
						})
						.then((r) => {
							d.hide();
							const m = r.message;
							const box = $("<div>");
							$("<p>").text(m.bound ? __("Works for 7 days, for one person.") : __("Works for 3 days. You confirm each person.")).appendTo(box);
							$("<input readonly class='form-control'>").attr("value", m.link).appendTo(box); // .val() is lost in .html()
							$("<img alt='QR code' style='width:180px;margin-top:12px'>").attr("src", m.qr).appendTo(box);
							if (m.emailed) $("<p>").text(__("The link is on its way by email.")).appendTo(box);
							frappe.msgprint({ title: __("Invitation link"), message: box.html() });
						});
				},
			});
			d.show();
		}, __("Clients"));
		frm.add_custom_button(__("Client chat"), () => frappe.set_route("client-chat"), __("Clients"));
	},
});
