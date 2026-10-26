#!/usr/bin/env bash
# A staging run-through on this machine (P1-19): the delivery image and compose stack exactly as deployed, behind
# real TLS from the proxy's internal CA, at https://staging.localhost:8443. Then a backup, a restore drill and
# deploy/check-staging.sh (G-48).
#
#   bash deploy/staging.sh up      create the settings (once), start, create the site, seed the check accounts
#                                  (deploy/seed-check.sh) and the go-live stand-ins; CW_KEEP_DEV=1 leaves ws-dev running
#   bash deploy/staging.sh drill   take a backup now and run the restore drill
#   bash deploy/staging.sh check   bash deploy/check-staging.sh
#   bash deploy/staging.sh routes  bash deploy/check-routes.sh (P2-07: the route findings on the delivery image)
#   bash deploy/staging.sh stop    stop the stack (volumes kept)
#
# Settings and secrets live in ~/.construction-workspace/staging/staging.env, outside the repository; secrets are
# generated once and never printed.
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep container paths as written
cd "$(dirname "$0")"

DIR="$HOME/.construction-workspace/staging"
ENV_FILE="$DIR/staging.env"
command -v cygpath >/dev/null 2>&1 && ENV_FILE="$(cygpath -m "$ENV_FILE")"  # docker.exe reads C:/... paths
export CW_ENV_FILE="$ENV_FILE"
hostpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }
secret() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

make_env() {
	mkdir -p "$DIR/backups" "$DIR/nas"
	touch "$DIR/nas/.cw-offsite-target"  # the stand-in NAS is "mounted" by definition (staging only)
	chmod 700 "$DIR" 2>/dev/null || true
	[ -f "$ENV_FILE" ] && return
	umask 077
	cat > "$ENV_FILE" <<EOF
COMPOSE_PROJECT_NAME=cw-staging
APP_IMAGE=construction-workspace:core-office
RENDERER_IMAGE=construction-workspace:renderer
SITE_NAME=staging.localhost
TLS_ISSUER=internal
HTTP_PORT=8880
HTTPS_PORT=8443
BACKUP_DIR=$(hostpath "$DIR/backups")
OFFSITE_DIR=$(hostpath "$DIR/nas")
OFFSITE_MUST_BE_MOUNT=0
CA_FILE=$(hostpath "$DIR/root.crt")
DB_ROOT_PASSWORD=$(secret)
ADMIN_PASSWORD=$(secret)
ONLYOFFICE_JWT_SECRET=$(secret)
CHECK_USER=staging-check@example.com
CHECK_PASSWORD=$(secret)
CHECK_CLIENT=staging-client@example.com
CHECK_CLIENT_PASSWORD=$(secret)
EOF
	echo ">> wrote $ENV_FILE (secrets generated)"
}

# A settings file from before P3-75 has no renderer image: add the one deploy/build.sh builds.
renderer_env() {
	grep -q '^RENDERER_IMAGE=' "$ENV_FILE" && return
	printf 'RENDERER_IMAGE=construction-workspace:renderer\n' >> "$ENV_FILE"
	echo ">> added RENDERER_IMAGE to $ENV_FILE"
}

# A settings file from before P3-10 has no firm name or privacy contact (D-218): add staging stand-ins.
firm_env() {
	grep -q '^COMPANY_NAME=' "$ENV_FILE" || printf 'COMPANY_NAME=Staging Builders
' >> "$ENV_FILE"
	grep -q '^PRIVACY_EMAIL=' "$ENV_FILE" || printf 'PRIVACY_EMAIL=privacy@staging.example.com
' >> "$ENV_FILE"
}

load() {
	set -a
	# shellcheck disable=SC1090
	. "$ENV_FILE"
	set +a
	C=(docker compose --env-file "$ENV_FILE" -f compose.yml --profile office)
}

# Staging only: what the office server gets from people (the outgoing mail account, confirmed by a code; the owner
# finishing the set-up wizard), so check-golive.sh can pass here. The account points at a host that does not exist
# and is never confirmed by mail; nothing here runs on a real site.
golive_standins() {
	local out
	out=$("${C[@]}" exec -T backend bash -c "bench --site $SITE_NAME console" 2>&1 <<'PY'
from frappe.utils import now_datetime
name = frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1})
if not name:
    acc = frappe.get_doc({"doctype": "Email Account", "email_account_name": "Staging outgoing", "email_id": "mail@staging.example.com",
        "enable_outgoing": 1, "default_outgoing": 1, "smtp_server": "smtp.staging.example.com", "smtp_port": 587, "use_tls": 1,
        "no_smtp_authentication": 1, "enable_incoming": 0})
    acc.db_insert()  # no validate: it would sign in to the server
    name = acc.name
acc = frappe.get_doc("Email Account", name)
frappe.db.set_global("cc_mail_confirmed", f"{acc.name}|{acc.modified}")
if not frappe.db.get_singles_dict("Firm Settings").get("setup_finished_on"):
    frappe.db.set_single_value("Firm Settings", "setup_finished_on", now_datetime())
frappe.db.commit()
print("STANDINS_READY")
PY
)
	echo "$out" | grep -q STANDINS_READY || { echo "the staging stand-ins failed:"; echo "$out" | tail -20; exit 1; }
	echo ">> staging stand-ins ready (outgoing mail account, set-up finished)"
}

case "${1:-up}" in
	up)
		make_env
		renderer_env
		firm_env
		load
		# Memory: the dev stack is stopped (never removed) while staging runs, unless CW_KEEP_DEV=1 (its tests are running).
		[ "${CW_KEEP_DEV:-0}" = 1 ] || docker compose -p ws-dev stop >/dev/null 2>&1 || true
		"${C[@]}" up -d
		bash init-site.sh
		for _ in $(seq 1 30); do
			"${C[@]}" exec -T proxy test -f /data/caddy/pki/authorities/local/root.crt && break
			sleep 2
		done
		"${C[@]}" exec -T proxy cat /data/caddy/pki/authorities/local/root.crt > "$DIR/root.crt"
		bash seed-check.sh
		load
		golive_standins
		echo ">> staging is up: https://$SITE_NAME:$HTTPS_PORT (trust $DIR/root.crt to browse it)"
		;;
	drill)
		load
		"${C[@]}" exec -T backup bash /usr/local/bin/cw-backup.sh
		latest="$(ls -1d "$DIR/backups"/20* | sort | tail -1)"
		bash restore.sh --drill "$latest"
		;;
	check)
		bash check-staging.sh
		;;
	routes)
		BOTH_PRESENTERS=1 bash check-routes.sh
		;;
	stop)
		load
		"${C[@]}" stop
		;;
	*)
		echo "usage: staging.sh up|drill|check|routes|stop" >&2
		exit 2
		;;
esac
