#!/usr/bin/env bash
# Create and configure the site of a deployed stack (P1-19). Idempotent: an existing site is migrated and
# reconfigured, never recreated. Run on the host, after `docker compose ... up -d`:
#
#   CW_ENV_FILE=/path/to/stack.env bash deploy/init-site.sh
#
# The env file (outside the repository) holds SITE_NAME, DB_ROOT_PASSWORD, ADMIN_PASSWORD, ONLYOFFICE_JWT_SECRET;
# COUNTRY, TIMEZONE and CURRENCY default to the Philippines. COMPANY_NAME and PRIVACY_EMAIL, when set, become the site
# config cc_company_name and cc_privacy_email (D-210, D-218), the set-up wizard's pre-fill. Secrets are passed to the containers by variable name
# and never printed. Frappe only: ERPNext is not installed (D-104).
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep container paths as written
cd "$(dirname "$0")"

ENV_FILE="${CW_ENV_FILE:?set CW_ENV_FILE to the env file of the stack}"
command -v cygpath >/dev/null 2>&1 && ENV_FILE="$(cygpath -m "$ENV_FILE")"  # docker.exe reads C:/... paths
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
: "${SITE_NAME:?}" "${DB_ROOT_PASSWORD:?}" "${ADMIN_PASSWORD:?}"
C=(docker compose --env-file "$ENV_FILE" -f compose.yml)
[ -n "${ONLYOFFICE_JWT_SECRET:-}" ] && C+=(--profile office)
B=("${C[@]}" exec -T backend)

for _ in $(seq 1 100); do
	st=$("${C[@]}" ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' | awk '$1=="configurator"{print $2, $3}')
	[ "$st" = "exited 0" ] && break
	sleep 3
done
[ "$st" = "exited 0" ] || { echo "configurator did not finish: $st" >&2; exit 1; }

if "${B[@]}" test -d "sites/$SITE_NAME"; then
	echo ">> site $SITE_NAME exists: migrating"
	"${B[@]}" bench --site "$SITE_NAME" migrate
else
	echo ">> creating $SITE_NAME (Frappe + construction_core + construction_shell, no ERPNext: D-104); this takes a few minutes"
	"${C[@]}" exec -T -e DB_ROOT_PASSWORD -e ADMIN_PASSWORD backend bash -c \
		'bench new-site "'"$SITE_NAME"'" --mariadb-user-host-login-scope=% \
			--db-root-password "$DB_ROOT_PASSWORD" --admin-password "$ADMIN_PASSWORD" \
			--install-app construction_core --install-app construction_shell'
	# Frappe's own setup: language, country, time zone, currency.
	args=$(printf '{"args": {"language": "English", "country": "%s", "timezone": "%s", "currency": "%s"}}' 		"${COUNTRY:-Philippines}" "${TIMEZONE:-Asia/Manila}" "${CURRENCY:-PHP}")
	"${B[@]}" bench --site "$SITE_NAME" execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete --kwargs "$args"
fi

# A site made before P2-02 gets the shell once (the image carries it).
if ! "${B[@]}" bench --site "$SITE_NAME" list-apps 2>/dev/null | grep -q '^construction_shell'; then
	echo ">> installing construction_shell on $SITE_NAME"
	"${B[@]}" bench --site "$SITE_NAME" install-app construction_shell
fi
# DR-2: a route rule change is a deploy event. Every deploy clears the route and website 404 caches (D-114).
"${B[@]}" bench --site "$SITE_NAME" execute construction_shell.deploy.clear_route_caches >/dev/null

# The encryption key exists from the start (Frappe otherwise creates it at the first encrypted value), so every
# backup set carries it and a restore drill can prove it.
"${B[@]}" bench --site "$SITE_NAME" execute frappe.utils.password.get_encryption_key >/dev/null
# Links and images in mail and the portal use the public HTTPS address, its port included; the scheduler runs.
"${B[@]}" bench --site "$SITE_NAME" set-config host_name "https://$SITE_NAME$([ "${HTTPS_PORT:-443}" = 443 ] || echo ":$HTTPS_PORT")" >/dev/null
"${B[@]}" bench --site "$SITE_NAME" scheduler enable >/dev/null
# D-017, D-417 (P3-75): the upload ceiling is 250 MB for model files; the app holds every other type to 100 MB.
"${B[@]}" bench --site "$SITE_NAME" set-config -p max_file_size 262144000 >/dev/null
"${B[@]}" bench use "$SITE_NAME" >/dev/null
# D-218: the firm's name and privacy contact, passed by variable name.
[ -n "${COMPANY_NAME:-}" ] && "${C[@]}" exec -T -e COMPANY_NAME backend bash -c \
	'bench --site "'"$SITE_NAME"'" set-config cc_company_name "$COMPANY_NAME" >/dev/null'
[ -n "${PRIVACY_EMAIL:-}" ] && "${C[@]}" exec -T -e PRIVACY_EMAIL backend bash -c \
	'bench --site "'"$SITE_NAME"'" set-config cc_privacy_email "$PRIVACY_EMAIL" >/dev/null'
# P3-10 (check-golive.sh): no tracebacks for anyone; uploads only of the types the app works with, so a System Manager
# cannot publish an .html, .svg or .js a browser would run on this origin. Types added in Desk are kept; those three
# are always taken out.
"${B[@]}" bench --site "$SITE_NAME" console >/dev/null <<'PY'
frappe.db.set_single_value("System Settings", "allow_error_traceback", 0)
base = set("""PDF JPG JPEG PNG WEBP GIF HEIC HEIF TIF TIFF BMP DOC DOCX DOCM DOTX XLS XLSX XLSM PPT PPTX ODT ODS ODP RTF TXT
CSV DWG DXF DWF DWFX RVT RFA IFC SKP NWD NWC MPP DGN KMZ M4A OGG WEBA WEBM MP3 WAV MP4 MOV ZIP MSG EML""".split())
now = set((frappe.db.get_single_value("System Settings", "allowed_file_extensions") or "").upper().split())
frappe.db.set_single_value("System Settings", "allowed_file_extensions",
    "\n".join(sorted((now | base) - {"HTML", "HTM", "XHTML", "SHTML", "SVG", "SVGZ", "JS", "MJS"})))
frappe.db.commit()

PY

if [ -n "${ONLYOFFICE_JWT_SECRET:-}" ]; then
	# P1-17: the office editor talks to the Document Server over the internal network only.
	"${C[@]}" exec -T -e ONLYOFFICE_JWT_SECRET backend bash -c \
		'bench --site "'"$SITE_NAME"'" set-config cc_office_jwt_secret "$ONLYOFFICE_JWT_SECRET" >/dev/null'
	"${B[@]}" bench --site "$SITE_NAME" set-config cc_office_internal_ds "http://documentserver" >/dev/null
	"${B[@]}" bench --site "$SITE_NAME" set-config cc_office_internal_site "http://frontend:8080" >/dev/null
fi

"${C[@]}" restart backend websocket queue-short queue-long queue-thumbs scheduler >/dev/null
"${C[@]}" restart frontend >/dev/null  # nginx resolves the backend once
echo ">> installed apps:"
"${B[@]}" bench --site "$SITE_NAME" list-apps
echo ">> https://$SITE_NAME is ready"
