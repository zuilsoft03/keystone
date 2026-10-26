#!/usr/bin/env bash
# Seed the MVP demo on dev.localhost (idempotent). The demo users' password is generated once into dev/.env
# (git-ignored) as DEMO_PASSWORD and passed to the container by name, never printed.
#
# Usage (from the repo root, with the stack up):  bash dev/seed-demo.sh
set -euo pipefail
cd "$(dirname "$0")"
if ! grep -q '^DEMO_PASSWORD=' .env; then
  printf 'DEMO_PASSWORD=%s\n' "$(head -c 18 /dev/urandom | base64 | tr -d '/+=')" >> .env
  echo ">> added DEMO_PASSWORD to dev/.env"
fi
set -a; . ./.env; set +a
MSYS_NO_PATHCONV=1 docker compose -p ws-dev -f docker-compose.yml --env-file .env exec -T -e DEMO_PASSWORD \
  -w /home/frappe/frappe-bench/sites backend /home/frappe/frappe-bench/env/bin/python - < seed_demo.py
echo ">> open http://localhost:${DEV_HTTP_PORT:-9600} (staff: /app, client: /portal); the password is DEMO_PASSWORD in dev/.env"
