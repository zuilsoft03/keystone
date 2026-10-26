#!/usr/bin/env bash
# G-38: the deploy profiles pin every SHA and digest, and only `full` ships ffmpeg (DR-1, D-083).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=""
for c in python3 py python; do  # the first interpreter that runs (Windows has a python3 stub that does not)
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "no Python interpreter found" >&2; exit 1; }
exec "$PY" deploy/verify_pins.py
