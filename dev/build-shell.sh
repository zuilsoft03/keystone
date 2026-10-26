#!/usr/bin/env bash
# Build the shell app (apps/construction_shell/frontend) for the dev stack (P2-02, D-111).
#
# It runs in the same pinned Node image as the delivery image's shell-build stage, never on the host: `npm ci` installs
# exactly the packages in package-lock.json, each checked against its integrity hash, then `vite build`. The output
# goes to apps/construction_shell/construction_shell/public/shell/ (not committed), which nginx serves at
# /assets/construction_shell/shell/. The npm download cache is a Docker volume (cw-npm-cache); `npm ci` still checks
# every package against the lockfile.
#
# Usage (from the repo root):  bash dev/build-shell.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep container paths as written
cd "$(dirname "$0")/.."
. dev/shell-images.sh
APP="apps/construction_shell"
HOST_APP="$APP"
command -v cygpath >/dev/null 2>&1 && HOST_APP="$(cygpath -m "$PWD/$APP")"
OUT="$APP/construction_shell/public/shell"
rm -rf "$OUT" && mkdir -p "$OUT"

# The sources are copied into the container, so node_modules never lands on the host's bind mount.
docker run --rm -v "$HOST_APP:/app:ro" -v "$HOST_APP/construction_shell/public/shell:/out" -v cw-npm-cache:/root/.npm \
	"$NODE_IMAGE" sh -euc '
		mkdir -p /work/frontend /work/construction_shell
		cp -r /app/frontend/. /work/frontend/ && rm -rf /work/frontend/node_modules /work/frontend/dist
		cp /app/construction_shell/sections.json /app/construction_shell/words.json /work/construction_shell/
		cd /work/frontend
		npm ci --ignore-scripts --no-audit --no-fund --loglevel=error
		npx vite build --logLevel warn
		cp -r dist/. /out/'
test -f "$OUT/.vite/manifest.json" || { echo "build-shell.sh: no manifest in $OUT" >&2; exit 1; }
echo ">> built the shell into $OUT"
