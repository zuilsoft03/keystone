#!/usr/bin/env bash
# The check accounts of a deployed stack (P1-19, P2-07; P3-10 moved them here from staging.sh, so the office server
# runs the same step). Idempotent. Run on the host after deploy/init-site.sh:
#
#   CW_ENV_FILE=/path/to/stack.env bash deploy/seed-check.sh
#
# Makes a staff account (Construction Manager) with a project "Staging check" and one spreadsheet, used by
# check-staging.sh, and a client contact of that project, used by check-routes.sh. Missing CHECK_* settings are added
# to the env file with generated passwords (never printed); OFFICE_FILE is written there.
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep container paths as written
cd "$(dirname "$0")"

ENV_FILE="${CW_ENV_FILE:?set CW_ENV_FILE to the env file of the stack}"
command -v cygpath >/dev/null 2>&1 && ENV_FILE="$(cygpath -m "$ENV_FILE")"
secret() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
add() {  # add <NAME> <value>: only when the file has no such line
	grep -q "^$1=" "$ENV_FILE" && return
	(umask 077; printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE")
	echo ">> added $1 to $ENV_FILE"
}
add CHECK_USER staging-check@example.com
add CHECK_PASSWORD "$(secret)"
add CHECK_CLIENT staging-client@example.com
add CHECK_CLIENT_PASSWORD "$(secret)"
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
C=(docker compose --env-file "$ENV_FILE" -f compose.yml)
[ -n "${ONLYOFFICE_JWT_SECRET:-}" ] && C+=(--profile office)

out=$("${C[@]}" exec -T -e CHECK_USER -e CHECK_PASSWORD backend bash -c "bench --site $SITE_NAME console" 2>&1 <<'PY'
import io, os
from openpyxl import Workbook
from frappe.utils.password import update_password
email = os.environ["CHECK_USER"]
if not frappe.db.exists("User", email):
    frappe.get_doc({"doctype": "User", "email": email, "first_name": "Staging", "last_name": "Check", "user_type": "System User", "send_welcome_email": 0, "roles": [{"role": "Construction Manager"}]}).insert(ignore_permissions=True)
update_password(email, os.environ["CHECK_PASSWORD"])
name = frappe.db.get_value("Construction Project", {"project_name": "Staging check"})
if not name:
    frappe.set_user(email)
    name = frappe.get_doc({"doctype": "Construction Project", "project_name": "Staging check", "cc_contract_signed_on": frappe.utils.today()}).insert().name
frappe.set_user(email)
fid = frappe.db.get_value("File", {"cc_project": name, "file_name": "Check sheet.xlsx"})
if not fid:
    from construction_core.providers.storage import FileStorage
    wb = Workbook(); wb.active["A1"] = "Staging check"; buf = io.BytesIO(); wb.save(buf)
    fid = FileStorage().put(f"Projects/{name}/01_Contract", "Check sheet.xlsx", buf.getvalue(), project=name)
frappe.db.commit()
print("OFFICE_FILE=" + fid)
PY
)
fid=$(echo "$out" | sed -n 's/.*OFFICE_FILE=\([0-9a-z]*\).*/\1/p' | tail -1)
[ -n "$fid" ] || { echo "seeding the check account failed:"; echo "$out" | tail -20; exit 1; }
sed -i '/^OFFICE_FILE=/d' "$ENV_FILE"
echo "OFFICE_FILE=$fid" >> "$ENV_FILE"
echo ">> check account and office file ready"

# The client, through the core's own add_client as the staff check account. The portal stays on for the project.
out=$("${C[@]}" exec -T -e CHECK_USER -e CHECK_CLIENT -e CHECK_CLIENT_PASSWORD backend bash -c "bench --site $SITE_NAME console" 2>&1 <<'PY'
import os
from frappe.utils.password import update_password
from construction_core.clients import add_client
staff, client = os.environ["CHECK_USER"], os.environ["CHECK_CLIENT"]
name = frappe.db.get_value("Construction Project", {"project_name": "Staging check"})
frappe.set_user(staff)
if not frappe.db.exists("Project Member", {"parent": name, "user": client}):
    add_client(name, client, "Staging Client")
frappe.set_user("Administrator")
update_password(client, os.environ["CHECK_CLIENT_PASSWORD"])
frappe.db.set_value("Workspace Config", name, "client_portal_enabled", 1)
frappe.db.commit()
print("CLIENT_READY=" + name)
PY
)
echo "$out" | grep -q 'CLIENT_READY=' || { echo "seeding the check client failed:"; echo "$out" | tail -20; exit 1; }
echo ">> check client ready"
