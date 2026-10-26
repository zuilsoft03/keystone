#!/usr/bin/env bash
# Build the base image for development (D-083, D-087, D-104): Frappe only. WITH_ERPNEXT=1 adds ERPNext (the `full`
# profile and the P1-22 coexistence check); construction_core never needs it.
#
# The recipe is frappe_docker's, plus the pinning layer from phase0/sandbox/Containerfile.pinned (D-013,
# D-025): `bench init --apps_path` honours only `url` and `branch`, so the exact revisions are checked out
# after the clone and recorded in /home/frappe/frappe-bench/apps-versions.json inside the image.
#
# Usage (from the repo root):  bash dev/build-core-image.sh            (Frappe only)
#                              WITH_ERPNEXT=1 IMAGE_TAG=ws-dev/frappe:core-erpnext bash dev/build-core-image.sh
set -euo pipefail
cd "$(dirname "$0")"

IMAGE_TAG="${IMAGE_TAG:-ws-dev/frappe:core}"
FRAPPE_REF="${FRAPPE_REF:-f20f92d29706510551b4438cc196b0323a7f1a92}"    # v16.50.0 (phase0/environment.md)
ERPNEXT_REF="${ERPNEXT_REF:-7474d9e786277383de1242ab882f16856d17a9c9}"  # v16.50.0, used only with WITH_ERPNEXT=1
WITH_ERPNEXT="${WITH_ERPNEXT:-0}"
FRAPPE_DOCKER=.cache/frappe_docker

# --- 1. canonical build context, with LF endings regardless of the host's git config ---
if [ ! -d "$FRAPPE_DOCKER/.git" ]; then
  mkdir -p .cache
  git -c core.autocrlf=false -c core.eol=lf clone --depth 1 https://github.com/frappe/frappe_docker "$FRAPPE_DOCKER"
fi
echo ">> frappe_docker at $(git -C "$FRAPPE_DOCKER" rev-parse HEAD)"
find "$FRAPPE_DOCKER/resources" -type f \( -name '*.sh' -o -name '*.conf' -o -name '*.template' \) \
  -exec sed -i 's/\r$//' {} +

if [ "$WITH_ERPNEXT" = 1 ]; then
  printf '[{"url": "https://github.com/frappe/erpnext", "branch": "version-16"}]\n' > .cache/apps.json
else
  : > .cache/apps.json  # empty: bench init installs Frappe alone (D-104)
  ERPNEXT_REF=""
fi

# BuildKit leaves secret mounts out of its cache key: the apps list must bust the `bench init` layer itself.
echo ">> pinning: frappe=$FRAPPE_REF erpnext=${ERPNEXT_REF:-none}"
DOCKER_BUILDKIT=1 docker build \
  --build-arg FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg FRAPPE_BRANCH=version-16 \
  --build-arg PYTHON_VERSION=3.14 \
  --build-arg PYTHON_DIGEST="${PYTHON_DIGEST:-}" \
  --build-arg NODE_VERSION=24 \
  --build-arg FRAPPE_REF="$FRAPPE_REF" \
  --build-arg ERPNEXT_REF="$ERPNEXT_REF" \
  --build-arg CACHE_BUST="apps-$(sha256sum .cache/apps.json | cut -c1-16)" \
  --secret id=apps_json,src=.cache/apps.json \
  -t "$IMAGE_TAG" \
  -f Containerfile.core \
  "$FRAPPE_DOCKER"

echo ">> built $IMAGE_TAG; recorded pins (read from inside the image):"
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint cat "$IMAGE_TAG" /home/frappe/frappe-bench/apps-versions.json
