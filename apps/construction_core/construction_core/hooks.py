app_name = "construction_core"
app_title = "Construction Core"
app_publisher = "Construction Workspace"
app_description = "Project-scoped construction domain, permissions, storage and Discuss threads for Frappe/ERPNext v16"
app_email = "maintainers@construction-workspace.invalid"
app_license = "agpl-3.0"

# Apps
# ------------------

required_apps = []  # Frappe alone (D-104); construction_core never requires an adapter or ERPNext (D-083)

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "construction_core",
# 		"logo": "/assets/construction_core/logo.png",
# 		"title": "Construction Core",
# 		"route": "/construction_core",
# 		"has_permission": "construction_core.api.permission.has_app_permission",
# 	}
# ]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `construction_core/dock/construction_core/construction_core.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/construction_core/css/construction_core.css"
# app_include_js = "/assets/construction_core/js/construction_core.js"

# include js, css files in header of web template
# web_include_css = "/assets/construction_core/css/construction_core.css"
# web_include_js = "/assets/construction_core/js/construction_core.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "construction_core/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "construction_core/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "construction_core.utils.jinja_methods",
# 	"filters": "construction_core.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "construction_core.install.before_install"
# after_install = "construction_core.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "construction_core.uninstall.before_uninstall"
# after_uninstall = "construction_core.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "construction_core.utils.before_app_install"
# after_app_install = "construction_core.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "construction_core.utils.before_app_uninstall"
# after_app_uninstall = "construction_core.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "construction_core.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "construction_core.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["construction_core.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"construction_core.tasks.all"
# 	],
# 	"daily": [
# 		"construction_core.tasks.daily"
# 	],
# 	"hourly": [
# 		"construction_core.tasks.hourly"
# 	],
# 	"weekly": [
# 		"construction_core.tasks.weekly"
# 	],
# 	"monthly": [
# 		"construction_core.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "construction_core.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Construction Task": "construction_core.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "construction_core.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Construction Task": "construction_core.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["construction_core.utils.before_request"]
# after_request = ["construction_core.utils.after_request"]

# P3-13 (R-13; D-200, D-202): every request of a turned-off account, or of a session older than its last turn-off or
# on, is refused and its session deleted (Frappe checks `enabled` only when a session starts).
auth_hooks = ["construction_core.accounts.sessions.check_session"]
on_session_creation = [
	"construction_core.accounts.sessions.refuse_new_session",  # D-203: every sign-in path
	"construction_core.accounts.visibility.refuse_client_without_project",  # P3-15 (D-206)
]

# Job Events
# ----------
# before_job = ["construction_core.utils.before_job"]
# after_job = ["construction_core.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"construction_core.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# ---------------------------------------------------------------------------------------------------------
# construction_core (P1-02): project-scoped access, ARCHITECTURE §2.1-§2.3, DR-6, DR-7

after_migrate = ["construction_core.accounts.settings.apply", "construction_core.accounts.sessions.ensure_user_index"]  # P3-14 (D-204): the pins hold after an upgrade
before_install = "construction_core.setup.install.before_install"  # our roles exist before the doctypes sync
after_install = "construction_core.setup.install.after_install"

_SCOPED = [
	"Construction Project", "Construction Task", "File", "Workspace Config", "Project Document", "BOQ", "WBS Node",
	"RFI", "Submittal", "Variation Order", "Discuss Thread", "Discuss Message", "Discuss Anchor", "Discuss Read State",
	"Discuss Pointer", "Discuss Follow", "Whiteboard", "Whiteboard Version", "CAD Drawing", "Takeoff",
	"Discuss Attachment", "Discuss Ref", "Discuss Poll", "Discuss Poll Vote", "Discuss Reaction", "Discuss Message Version",
	"Discuss Removed Text", "File Request", "Approval Request", "Approval Event", "Approval Evidence Detail",
	"Client Decision",  # P3-77 (C3): the rename guard (CheckedRename) and refuse_named_rename come with it
]  # keep equal to permissions.SCOPED_DOCTYPES; slices add theirs (DR-6)

permission_query_conditions = {dt: "construction_core.permissions.query_conditions" for dt in _SCOPED}
has_permission = {dt: "construction_core.permissions.can_access" for dt in _SCOPED}
# P3-15 (D-194, D-206): staff see the team and their own projects' clients; ANDed with Frappe's own User rules
permission_query_conditions["User"] = "construction_core.accounts.visibility.user_query_conditions"
has_permission["User"] = "construction_core.accounts.visibility.user_has_permission"

extend_doctype_class = {dt: ["construction_core.overrides.realtime.DocRoomOnly"] for dt in _SCOPED}  # P1-09, DR-8
extend_doctype_class["File"].insert(0, "construction_core.overrides.file.ProjectScopedFile")
extend_doctype_class["Construction Project"].insert(0, "construction_core.overrides.project.ProjectMembership")
extend_doctype_class["Notification Log"] = ["construction_core.overrides.realtime.OwnRoomOnly"]  # P3-06, DR-8
# P3-76 (bypass-7): a rename runs its checks; force, and renaming a User, are a System Manager's
for _dt in (*_SCOPED, "DocType", "User"):
	extend_doctype_class.setdefault(_dt, []).append("construction_core.overrides.rename.CheckedRename")
for _dt in ("Notification", "Webhook"):  # P3-76 round 5: a rule's condition preview under the safe-render flag
	extend_doctype_class.setdefault(_dt, []).append("construction_core.overrides.preview.SafePreview")
notification_skip_email_types = ["Alert"]  # D-160: a bell notice is never emailed, whatever Frappe's own list holds

# P3-76 (bypass-8): a Print Format's template renders with the live Document in context; render it under the safe-render
# flag so a template cannot write a ledger column (frappe.qb refused; LedgerRow.before_change backstops db_set)
pdf_body_html = "construction_core.overrides.print.pdf_body_html"

override_whitelisted_methods = {
	# P1-14 audit: clients never join realtime document rooms (presence and doc events); see discuss/api.py
	"frappe.realtime.has_permission": "construction_core.discuss.api.realtime_has_permission",
	# P3-04 audit (D-168): a record's Desk activity (versions, comments, attachments, follow digests) is for the team
	**{f"frappe.desk.form.{m}": f"construction_core.overrides.desk.{m.split('.')[-1]}" for m in (
		"load.getdoc", "load.get_docinfo", "load.get_filtered_attachments", "load.get_communications",
		"activity.get_activity_timeline", "activity.get_more_email_activities", "activity.get_more_milestone_activities",
		"utils.add_comment", "utils.update_comment", "utils.update_comment_publicity", "utils.remove_attach",
		"document_follow.follow_document", "document_follow.update_follow")},
	# P3-63 audit (D-412): linked_with's hidden_count counts the linked rows the caller may not read
	"frappe.desk.form.linked_with.get": "construction_core.overrides.desk.linked_with",
	# P3-07 (D-180): Frappe's zip_files checks only Frappe's own File rule, never our project check. Both names it
	# answers to, since each resolves to its own last override.
	"frappe.core.api.file.zip_files": "construction_core.overrides.file.zip_files",
	"frappe.core.doctype.file.file.zip_files": "construction_core.overrides.file.zip_files",
	# P3-07 review (C2): a client's upload in one piece, so it reaches File.before_insert and the scan (D-183)
	"upload_file": "construction_core.overrides.file.upload_file",
	"frappe.handler.upload_file": "construction_core.overrides.file.upload_file",
	# P3-14 (D-204): one way in, our own invitations (R-13)
	**{m: "construction_core.accounts.guard.refused" for m in (
		"frappe.core.doctype.user.user.sign_up",
		"frappe.core.api.user_invitation.accept_invitation", "frappe.core.api.user_invitation.invite_by_email",
		# P3-20 (D-228): it let a session clear its own authenticator; two_step.reset_for is the lost-phone switch-off
		"frappe.twofactor.reset_otp_secret")},
	"frappe.website.doctype.web_form.web_form.accept": "construction_core.accounts.guard.web_form_accept",
	# P3-76 round 4: frappe.rename_doc passes force straight through (bypass-7); frappe.email.relink points a
	# Communication at a reference by raw SQL, with no Communication hook (bypass-3)
	"frappe.rename_doc": "construction_core.overrides.rename.rename_doc",
	"frappe.email.relink": "construction_core.overrides.communication.relink",
	# P3-76 round 5 (D2, D3): a ledger row's _liked_by and _user_tags by set_value, and a reader's expressions against
	# a live Document, which keep a write made before their error
	"frappe.desk.like.toggle_like": "construction_core.overrides.tags.toggle_like",
	**{f"frappe.desk.doctype.tag.tag.{m}": f"construction_core.overrides.tags.{m}" for m in ("add_tag", "add_tags",
		"remove_tag")},
	"frappe.utils.print_format_generator.check_conditions": "construction_core.overrides.print.check_conditions",
	# P3-78 (approvals §4.5): a self-service change or reset is a credential event; a reset through the link the team
	# mailed to the verified address ends a re-confirmation
	"frappe.core.doctype.user.user.update_password": "construction_core.approvals.credentials.update_password",
}
# P3-76 round 5 (D1): the overrides above hold by the function, whatever name a request sends for it
before_request = ["construction_core.overrides.dispatch.refuse_replaced_alias",
	"construction_core.approvals.answer.note_idle"]  # P3-78 (§3.5 item 3): the idle hour, before Frappe resets it

doc_events = {
	"Construction Project": {
		"before_insert": "construction_core.permissions.add_creator_as_member",
		"validate": [
			"construction_core.workspace.validate_project",
			"construction_core.accounts.visibility.guard_members",  # P3-15 (D-198, D-206): clients join by invitation
			"construction_core.approvals.api.guard",  # P3-77 (§3.2): the approval set-up is server-owned
		],
		"after_insert": [
			"construction_core.permissions.sync_user_permissions",
			"construction_core.workspace.on_project_insert",
			"construction_core.discuss.rooms.on_project_insert",  # P3-73 (D-418): its Team and Client rooms
		],
		"on_update": [
			"construction_core.permissions.sync_user_permissions",
			"construction_core.approvals.api.on_project_update",  # P3-77 (A-1): a removed approver's row ends in the chain
		],
		"on_trash": [
			"construction_core.approvals.log.refuse_project_delete",  # P3-76 (D-427): first, before any cleanup
			"construction_core.permissions.cleanup_user_permissions",
			"construction_core.onboarding.invites.delete_project_invites",  # P3-16 (D-209)
			"construction_core.signin_pictures.on_project_trash",  # P3-34 (D-275): its sign-in pictures go with it
			"construction_core.discuss.rooms.on_project_trash",  # P3-73 (DR-7): its rooms, while nothing was said
		],
		"after_delete": "construction_core.approvals.log.refuse_project_delete",  # P3-76: a delete that skipped on_trash
	},
	"Approval Settings": {"validate": "construction_core.approvals.api.guard"},  # P3-77: the evidence mailbox
	"Approval Event": {"after_insert": "construction_core.approvals.card.on_event"},  # P3-78 (§3.12): the card follows the chain
	"File": {
		"before_validate": "construction_core.permissions.force_private",
		"validate": ["construction_core.permissions.validate_file", "construction_core.accounts.guard.guard_identity_file"],
		"on_update": "construction_core.permissions.revoke_foreign_shares",
		# P3-34 (D-275): a deleted render leaves the sign-in; P3-43: a deleted file takes its version rows with it;
		# P3-75 (§15.3): and its previews, the chat cards' too (before the version rows go)
		"on_trash": ["construction_core.signin_pictures.on_file_trash", "construction_core.previews.purge.on_file_trash",
			"construction_core.files.versions.on_file_trash"],
	},
	"Construction Task": {"on_update": "construction_core.permissions.revoke_foreign_shares"},
	"Whiteboard": {"on_trash": "construction_core.previews.purge.on_board_trash"},  # P3-75: its picture goes with it
	"DocShare": {"validate": "construction_core.permissions.validate_share"},
	# P3-76: no comment, assignment, tag or communication on a ledger row, so a client-readable request's _comments,
	# _assign, _user_tags and modified stay as the ledger wrote them; on every save too, so none is re-pointed at one.
	# A Communication Link saved on its own (frappe.client.save) too (bypass-3). Round 5 (D5): a docstatus 2 or 1 save
	# runs before_cancel or before_update_after_submit instead of before_validate. Communication: validate too, because
	# its controller adds timeline links (recipients' +doctype forms, contacts' Dynamic Links) after before_validate.
	**{dt: {ev: "construction_core.approvals.log.refuse_ledger_reference" for ev in ("before_validate", "before_cancel",
		"before_update_after_submit", *(("validate",) if dt == "Communication" else ()))}
		for dt in ("Comment", "ToDo", "Tag Link", "Communication Link", "Communication")},
	# round 5 (D6): no Dynamic Link names a ledger row (a Contact's links go on its emails' timelines)
	**{dt: {ev: "construction_core.approvals.log.refuse_ledger_link" for ev in ("before_validate", "before_cancel",
		"before_update_after_submit")} for dt in ("Contact", "Address", "Event", "Web Form Request", "Dynamic Link")},
	# round 4 (should-fix): a rule on a ledger doctype fires on every ledger insert/save ("*" hooks and run_method's
	# built-in dispatchers) and would break, write or attach a reference. Refused at configuration: Assignment Rule
	# and Milestone Tracker ("*" apply/evaluate_milestone), Notification (evaluate_alert), Automation Flow (16.50),
	# Webhook and Workflow (condition/payload/state against the live row); Auto Repeat (allow_auto_repeat can never be
	# set, refused cleanly); Document Naming Rule (it would seize the ledger's own naming on insert).
	**{dt: {"before_validate": "construction_core.approvals.log.refuse_ledger_automation"}
		for dt in ("Assignment Rule", "Notification", "Automation Flow", "Webhook", "Workflow", "Auto Repeat",
			"Milestone Tracker", "Document Naming Rule")},
	# P3-76 (bypass-1): the ledger doctypes are their JSON, changed by migrate only (never custom, a child table, a
	# Table field's rows, a role's permissions, or one of their own rows saved on its own)
	"DocType": {"before_validate": "construction_core.approvals.log.refuse_ledger_customization",
		"before_rename": "construction_core.approvals.log.refuse_ledger_customization"},
	**{dt: {"before_validate": "construction_core.approvals.log.refuse_ledger_customization"}
		for dt in ("Custom Field", "Property Setter", "Custom DocPerm", "DocPerm", "DocField",
			"DocType Action", "DocType Link", "DocType State")},  # the last three: Customize Form's own saves (round 4)
	# P3-76 (bypass-7): a rename runs its checks (validate_rename and before_rename), whatever route asks for it
	"*": {"before_rename": "construction_core.permissions.mark_checked_rename",
		"after_rename": "construction_core.permissions.refuse_unchecked_rename"},
	"User": {
		"before_validate": [
			"construction_core.accounts.guard.guard_client_identity",  # P3-14 (D-204)
			"construction_core.accounts.guard.guard_enabled",  # P3-15 (D-207)
			# P3-78 (approvals §4.5): a password set by someone else, before Frappe's validate clears new_password
			"construction_core.approvals.credentials.on_user_before_validate",
		],
		"before_rename": [
			"construction_core.accounts.guard.refuse_rename",  # P3-14 audit M1
			"construction_core.approvals.credentials.on_user_rename",  # P3-78 (§4.5): mailed to the old address
		],
		"validate": [
			"construction_core.accounts.visibility.refuse_mixed_roles",  # P3-15 (D-206)
			"construction_core.accounts.two_step.guard_role",  # P3-20 (D-229): the role only through the setup
			"construction_core.accounts.guard.refuse_client_api_key",  # P3-78 (§4.5, T6): no key signs a client in
		],
		"on_update": "construction_core.accounts.sessions.on_user_update",  # P3-13: the access stamp
	},
	"User Invitation": {"before_insert": "construction_core.accounts.guard.refused"},  # P3-14 review F3: every path
	# P1-09: workspace counts to each member's user room (DR-8)
	**{dt: {"on_update": "construction_core.core.counts.on_change", "on_trash": "construction_core.core.counts.on_change"}
		for dt in ("RFI", "Submittal", "Variation Order")},
}

# P2-04 audit 1-2: a child row changes only through its record's save (Frappe's REST endpoints save rows alone).
for _dt in (
	"Attachment Ref", "BOQ Line", "Distribution User", "Folder Template Item", "Project Member", "Submittal Revision",
	"Takeoff Item", "VO BOQ Delta", "Workspace Section", "File Request Item", "File Request Recipient",
	"Client Decision Option",
):  # keep equal to permissions.CHILD_DOCTYPES
	doc_events[_dt] = {
		"before_validate": "construction_core.permissions.refuse_direct_child_write",
		"on_trash": "construction_core.permissions.refuse_direct_child_write",
	}

# P1-08 re-audit: no save may take over another record's child rows (Frappe core moves them by name).
for _dt in _SCOPED:
	_ev = doc_events.setdefault(_dt, {})
	_bv = _ev.get("before_validate")
	_ev["before_validate"] = [
		"construction_core.permissions.refuse_foreign_rows",
		*([_bv] if isinstance(_bv, str) else _bv or []),
	]
	# P3-76 (D-427): a record named in an approval request keeps its name, and so does a project with approval records;
	# after_rename too, which rename_doc reaches with validate=False
	for _hook in ("before_rename", "after_rename"):
		_br = _ev.get(_hook)
		_ev[_hook] = ["construction_core.approvals.log.refuse_named_rename",
			*([_br] if isinstance(_br, str) else _br or [])]

for _dt in ("RFI", "Submittal", "Variation Order", "Project Document"):  # P3-06: notices captured in the saving request
	_ev = doc_events.setdefault(_dt, {})
	_ou = _ev.get("on_update")
	_ev["on_update"] = [*([_ou] if isinstance(_ou, str) else _ou or []), "construction_core.notifications.on_record_update"]

scheduler_events = {
	"daily": [
		"construction_core.construction_core.doctype.rfi.rfi.emit_overdue",  # rfi.overdue (§9.1)
		"construction_core.onboarding.jobs.daily",  # P3-22 (D-193, D-239): onboarding retention, catching up
		"construction_core.discuss.parts.file_requests.remind",  # P3-71 (D-379, D-384): file request reminders
		"construction_core.approvals.api.remind",  # P3-78 (approvals §3.10): reminders and the overdue bell
		"construction_core.approvals.routes.remind",  # P3-82 (approvals §14.3 item 8): internal steps past due
		"construction_core.approvals.digest.daily",  # P3-81 (approvals §4.6, §4.8): verify, digest, heads, retention
	],
	"hourly": [
		"construction_core.discuss.media.purge",  # P3-65 (D-389): unsent chat uploads, deleted 24 hours after upload
		"construction_core.previews.purge.sweep",  # P3-75 (§15.3): previews no row uses, and those of deleted files
		"construction_core.scan_holds.sweep",  # P3-75 (D-417): held bytes no hold names, and week-old refusals
	],
	"cron": {
		"*/5 * * * *": [
			"construction_core.previews.jobs.retry_due",  # P3-75 (§15.3): previews whose retry is due
			"construction_core.discuss.parts.attachments.rescan_due",  # P3-75 (D-417): large chat files' scans
			"construction_core.scan_holds.rescan_due",  # P3-75 (D-417): large Files sends' scans
			"construction_core.approvals.receipts.retry_due",  # P3-78 (approvals §3.6): receipts not sent yet
		],
	},
}

# P3-75 (§15.3): a file put in the bin or no longer shared with the client loses its previews (after the commit)
cc_event_handlers = {
	"storage.file_trashed": ["construction_core.previews.purge.on_file_event"],
	"storage.visibility_changed": ["construction_core.previews.purge.on_file_event"],
	# P3-69 (§3.9, D-420): design events as System cards in the record's thread or its room
	"document.published": ["construction_core.discuss.events.on_event"],
	"file.revised": ["construction_core.discuss.events.on_event"],
	"whiteboard.saved": ["construction_core.discuss.events.on_event"],
}

# P1-13: the portal claims the whole /portal namespace; every unknown path ends in our own 404 (DR-3, §3.2)
website_route_rules = [
	{"from_route": "/portal", "to_route": "ws_portal"},
	{"from_route": "/portal/<path:app_path>", "to_route": "ws_portal"},
	# P3-17 (D-214): the sign-in-free join page; every path below it is our own 404
	{"from_route": "/join", "to_route": "ws_join"},
	{"from_route": "/join/<path:app_path>", "to_route": "ws_join"},
	# P3-24 (D-251, D-252): sign-in and the password page drawn as the design's LoginA, on Frappe's own calls
	{"from_route": "/login", "to_route": "ws_login"},
	# P3-26 (D-264, D-265): the clients' sign-in, LoginB (a static segment, so it wins over /portal/<path>)
	{"from_route": "/portal/login", "to_route": "ws_login"},
	{"from_route": "/update-password", "to_route": "ws_login"},
]
# P3-22 (D-239): our onboarding records of a person, for Frappe's own personal-data tools
user_data_fields = [
	{"doctype": "Client Profile", "match_field": "account", "personal_fields": ["full_name", "mobile_no", "company_name"]},
	{"doctype": "Access Invite", "match_field": "email", "personal_fields": ["full_name"]},
	{"doctype": "Access Request", "match_field": "email", "personal_fields": ["full_name", "mobile_no", "company_name"]},
]
role_home_page = {"Construction Client": "portal"}  # clients land on the portal after login

# P1-14: client contacts and the client chat from the Project form (D-098)
doctype_js = {
	"Construction Project": "public/js/project.js",
	# P2-07: office files open in the workspace's editor (construction_shell's own Desk buttons, D-120).
}
