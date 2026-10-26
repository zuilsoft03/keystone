"""The join page's presenter (P3-17, D-214). construction_core's /join page calls it (hook cc_join_renderer); it returns
the shell's join app and the little the page may show before anything is proven: the product's and the company's names
(D-298, D-210) and the privacy contact. Nothing about any invitation: the app asks construction_core.onboarding.join
for that."""

from construction_core.onboarding import privacy
from construction_shell.workspace_page import brand_boot, shell_assets, tab_title

ENTRY = "src/join.js"


def render(context) -> dict | None:
	assets = shell_assets(ENTRY)
	if not assets:
		return None
	context.title = tab_title(context.get("title"))  # "Page · Product name" (D-299)
	return {**assets, "boot": {**brand_boot(), "privacy_email": privacy.contact()}}
