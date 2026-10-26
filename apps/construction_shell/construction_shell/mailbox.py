"""The evidence mailbox confirm page's presenter (P3-77). construction_core's /evidence-mailbox page calls it (hook
cc_mailbox_renderer); it returns the shell's mailbox app and the product's and the company's names (D-298, D-210), and
nothing about the mailbox: the app posts the link's token to construction_core.approvals.api.confirm_evidence_mailbox."""

from construction_shell.workspace_page import brand_boot, shell_assets, tab_title

ENTRY = "src/mailbox.js"


def render(context, entry: str = ENTRY) -> dict | None:
	assets = shell_assets(entry)
	if not assets:
		return None
	context.title = tab_title(context.get("title"))  # "Page · Product name" (D-299)
	return {**assets, "boot": brand_boot()}


def render_dispute(context) -> dict | None:
	"""P3-78 (approvals §3.7): the receipt's "This was not me" page (core's /approval-dispute, hook cc_dispute_renderer),
	the same shell and brand with its own app, which posts the link's token to construction_core.approvals.dispute."""
	return render(context, "src/dispute.js")
