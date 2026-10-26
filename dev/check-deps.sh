#!/usr/bin/env bash
# ARCHITECTURE §10 dependency rules, as a check (P1-01; the shell from P2-02). Exit 0 = all rules hold.
#   1. Our apps (construction_core, construction_shell) import no adapter (no `import ws_…` / `from ws_… import`, no
#      "ws_….x" dotted path).
#   2. Neither requires an adapter in hooks.py `required_apps`.
#   3. Both are independent of ERPNext (D-104), the shell requires only the core, and the core never references the
#      shell: dev/check_independence.py.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
APPS=(apps/construction_core apps/construction_shell)
hits=$(grep -REn --exclude-dir=node_modules --exclude-dir=shell --exclude-dir=dist \
	'^[[:space:]]*(from|import)[[:space:]]+ws_|["'\'']ws_[a-z]+\.' "${APPS[@]}" || true)
if [ -n "$hits" ]; then echo "FAIL rule 1: an app of ours references an adapter:"; echo "$hits"; fail=1; else echo "PASS rule 1: no adapter import"; fi
if grep -En '^required_apps.*ws_' apps/construction_core/construction_core/hooks.py apps/construction_shell/construction_shell/hooks.py; then echo "FAIL rule 2: an adapter is a required app"; fail=1; else echo "PASS rule 2: no adapter in required_apps"; fi
PY=""
for c in python3 py python; do  # the first interpreter that runs (Windows has a python3 stub that does not)
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then echo "FAIL rule 3: no Python interpreter"; fail=1; elif ! "$PY" dev/check_independence.py; then fail=1; fi
exit $fail
