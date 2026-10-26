#!/usr/bin/env bash
# Bring up ws-dev and make sure the site `dev.localhost` exists with construction_core and construction_shell installed
# (Frappe only, D-104; the shell from P2-02).
# Idempotent: a second run only starts the stack. Secrets are generated once into dev/.env (git-ignored)
# and passed into containers by variable name, never printed.
#
# Usage (from the repo root):  bash dev/up.sh
set -euo pipefail
cd "$(dirname "$0")"
SITE=dev.localhost

# D-290: on Windows, a Docker Desktop that did not exit cleanly leaves stale socket files that stop its next start.
# When the engine does not answer, the preflight clears them and starts Docker Desktop (never a reset).
if ! docker info >/dev/null 2>&1 && command -v powershell.exe >/dev/null 2>&1; then
  echo ">> Docker is not running: clearing stale sockets and starting it (dev/docker-preflight.ps1)"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$PWD/docker-preflight.ps1")"
fi
C=(docker compose -p ws-dev -f docker-compose.yml --env-file .env)

if [ ! -f .env ]; then
  gen() { head -c 24 /dev/urandom | base64 | tr -d '/+=' ; }
  printf 'DB_ROOT_PASSWORD=%s\nADMIN_PASSWORD=%s\n' "$(gen)" "$(gen)" > .env
  echo ">> wrote dev/.env (new secrets)"
fi
if ! grep -q '^ONLYOFFICE_JWT_SECRET=' .env; then
  printf 'ONLYOFFICE_JWT_SECRET=%s\n' "$(head -c 24 /dev/urandom | base64 | tr -d '/+=')" >> .env
  echo ">> added ONLYOFFICE_JWT_SECRET to dev/.env"
fi
set -a; . ./.env; set +a

# P2-02: the shell's built app (not committed) is served from the bind mount; build it once if it is missing.
[ -f ../apps/construction_shell/construction_shell/public/shell/.vite/manifest.json ] || bash build-shell.sh

"${C[@]}" up -d
echo ">> waiting for the configurator"
for _ in $(seq 1 60); do
  st=$("${C[@]}" ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' | awk '$1=="configurator"{print $2, $3}')
  [ "$st" = "exited 0" ] && break; sleep 3
done
[ "$st" = "exited 0" ] || { echo "configurator did not finish: $st" >&2; exit 1; }

if "${C[@]}" exec -T backend test -d "sites/$SITE"; then
  echo ">> site $SITE exists"
else
  echo ">> creating $SITE (Frappe + construction_core + construction_shell, no ERPNext: D-104); this takes a few minutes"
  "${C[@]}" exec -T -e DB_ROOT_PASSWORD -e ADMIN_PASSWORD backend bash -c \
    'bench new-site '"$SITE"' --mariadb-user-host-login-scope=% \
       --db-root-password "$DB_ROOT_PASSWORD" --admin-password "$ADMIN_PASSWORD" \
       --install-app construction_core --install-app construction_shell'
  # Frappe's own setup: language, country, time zone and currency (PHP).
  "${C[@]}" exec -T backend bench --site "$SITE" execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
    --kwargs '{"args": {"language": "English", "country": "Philippines", "timezone": "Asia/Manila", "currency": "PHP"}}'
  "${C[@]}" exec -T backend bench --site "$SITE" set-config allow_tests true
  "${C[@]}" exec -T backend bench --site "$SITE" set-config developer_mode 1
fi

# A site made before P2-02 gets the shell once.
if ! "${C[@]}" exec -T backend bench --site "$SITE" list-apps 2>/dev/null | grep -q '^construction_shell'; then
  echo ">> installing construction_shell on $SITE"
  "${C[@]}" exec -T backend bench --site "$SITE" install-app construction_shell
fi

# Apply our patches and fixtures on every start (idempotent).
"${C[@]}" exec -T backend bench --site "$SITE" migrate >/dev/null
# DR-2: a route rule change is a deploy event; clear the route and website 404 caches after every migrate.
"${C[@]}" exec -T backend bench --site "$SITE" execute construction_shell.deploy.clear_route_caches >/dev/null

# construction_core is bind-mounted; restart the Python services so they import the current code.
"${C[@]}" restart backend websocket queue-short >/dev/null
# nginx resolves the backend once; after a backend restart it would answer 502 until it is restarted too.
"${C[@]}" restart frontend >/dev/null
# P1-17: the office editor's settings (the secret by variable name; never printed)
"${C[@]}" exec -T -e ONLYOFFICE_JWT_SECRET backend bash -c \
  'bench --site '"$SITE"' set-config cc_office_jwt_secret "$ONLYOFFICE_JWT_SECRET" >/dev/null'
"${C[@]}" exec -T backend bench --site "$SITE" set-config cc_office_internal_ds "http://documentserver" >/dev/null
"${C[@]}" exec -T backend bench --site "$SITE" set-config cc_office_internal_site "http://frontend:8080" >/dev/null
echo ">> installed apps:"; "${C[@]}" exec -T backend bench --site "$SITE" list-apps
echo ">> ws-dev is up: http://localhost:${DEV_HTTP_PORT:-9600}"
