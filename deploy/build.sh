#!/usr/bin/env bash
# Build the delivery image of one deploy profile (DR-1, D-083) from its pins.
#
#   bash deploy/build.sh core            -> construction-workspace:core
#   bash deploy/build.sh core+office     -> construction-workspace:core-office
#   bash deploy/build.sh full            -> construction-workspace:full
#
# 1. The base (Frappe + ERPNext) is built by dev/build-core-image.sh with the profile's commits and Python digest.
# 2. deploy/Containerfile.pinned bakes construction_core and construction_shell in (the shell's app is built in its own
#    stage, from its lockfile, in the pinned Node image), plus the profile's build packages (full only).
# 3. P3-75: the renderer image, construction-workspace:renderer, from deploy/renderer/ (the same pinned Python base,
#    its two wheels by hash, the readers copied in), labelled with a digest of its inputs. deploy/compose.yml takes it as
#    RENDERER_IMAGE, so the server needs neither Docker Hub nor PyPI when the stack starts.
# Run `bash deploy/verify-pins.sh` first; this script refuses to build when it fails.
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILE="${1:?usage: deploy/build.sh <core|core+office|full>}"
PINS="deploy/profiles/$PROFILE/apps-versions.json"
[ -f "$PINS" ] || { echo "no such profile: $PROFILE" >&2; exit 1; }
bash deploy/verify-pins.sh

PY=""
for c in python3 py python; do  # the first interpreter that runs (Windows has a python3 stub that does not)
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "no Python interpreter found" >&2; exit 1; }
pin() { "$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {}, {'d': d}))" "$PINS" "$1"; }

FRAPPE_REF=$(pin 'd["apps"]["frappe"]["commit"]')
ERPNEXT_REF=$(pin 'd["apps"].get("erpnext", {}).get("commit", "")')  # only `full` carries ERPNext (D-104)
WITH_ERPNEXT=0; [ -n "$ERPNEXT_REF" ] && WITH_ERPNEXT=1
PYTHON_DIGEST="@$(pin 'd["base"]["python"].split("@")[1]')"
BUILD_PACKAGES=$(pin '" ".join(d["build_packages"])')
SHELL_NODE_IMAGE=$(pin 'd["base"]["shell_node"]')
TAG="construction-workspace:${PROFILE/+/-}"
BASE_TAG="construction-workspace/base:${FRAPPE_REF:0:12}-${ERPNEXT_REF:0:12}"
[ -n "$ERPNEXT_REF" ] || BASE_TAG="construction-workspace/base:${FRAPPE_REF:0:12}-frappe-only"

echo ">> base $BASE_TAG (frappe $FRAPPE_REF, erpnext $ERPNEXT_REF, python $PYTHON_DIGEST)"
IMAGE_TAG="$BASE_TAG" FRAPPE_REF="$FRAPPE_REF" ERPNEXT_REF="$ERPNEXT_REF" WITH_ERPNEXT="$WITH_ERPNEXT" PYTHON_DIGEST="$PYTHON_DIGEST" \
  bash dev/build-core-image.sh
BASE_ID=$(docker image inspect --format '{{.Id}}' "$BASE_TAG")

# BuildKit cannot take a bare image ID in FROM; the base tag names both commits, and its ID is logged and labelled.
echo ">> $TAG from $BASE_TAG = $BASE_ID (build packages: ${BUILD_PACKAGES:-none})"
DOCKER_BUILDKIT=1 docker build \
  --build-arg BASE_IMAGE="$BASE_TAG" \
  --label construction.base-id="$BASE_ID" \
  --build-arg PROFILE="$PROFILE" \
  --build-arg BUILD_PACKAGES="$BUILD_PACKAGES"   --build-arg SHELL_NODE_IMAGE="$SHELL_NODE_IMAGE" \
  -f deploy/Containerfile.pinned -t "$TAG" .
echo ">> built $TAG"

# P3-75: the renderer. Built from the repository root (the root .dockerignore keeps the context small).
RENDERER_INPUTS=(deploy/renderer/Containerfile deploy/renderer/requirements.txt deploy/renderer/server.py
  deploy/renderer/child.py apps/construction_core/construction_core/takeoff/dxf.py
  apps/construction_core/construction_core/previews/readers/*.py)
RENDERER_TAG="construction-workspace:renderer"
RENDERER_INPUT="$(cat "${RENDERER_INPUTS[@]}" | sha256sum | cut -c1-64)"
DOCKER_BUILDKIT=1 docker build -f deploy/renderer/Containerfile --label construction.renderer-inputs="$RENDERER_INPUT" \
  -t "$RENDERER_TAG" .
echo ">> built $RENDERER_TAG (inputs $RENDERER_INPUT; the stack's settings file names it as RENDERER_IMAGE)"
