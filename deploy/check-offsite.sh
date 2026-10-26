#!/usr/bin/env bash
# G-52 (P2-01, D-103, D-107): the newest backup set is also off the host, on the NAS share, intact; retention holds.
# Black-box, from the stack's settings file (default ~/.construction-workspace/staging/staging.env):
#   BACKUP_DIR, OFFSITE_DIR (the mounted NAS share), SITE_NAME, COMPOSE_PROJECT_NAME;
#   OFFSITE_MUST_BE_MOUNT=0 only on staging, whose "NAS" is a local stand-in folder.
# Prints PASS/FAIL per check; exits 1 on any failure. Run it as root on a Linux host (the sets are root-only).
# deploy/check-staging.sh runs the fail-safe cases of deploy/test-scripts.sh, the off-host ones included.
set -uo pipefail
unset MSYS_NO_PATHCONV  # Git Bash on Windows: native tools need their paths converted

ENV_FILE="${CW_ENV_FILE:-$HOME/.construction-workspace/staging/staging.env}"
command -v cygpath >/dev/null 2>&1 && ENV_FILE="$(cygpath -m "$ENV_FILE")"
MARKER=".cw-offsite-target"
fails=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; fails=$((fails + 1)); }
done_() { [ "$fails" -eq 0 ] && echo "OK: 0 failure(s)" || echo "FAILED: $fails failure(s)"; [ "$fails" -eq 0 ]; exit $?; }
is_set() { [[ "$1" =~ ^20[0-9]{6}T[0-9]{6}Z$ ]]; }
epoch() { local n="$1"; date -u -d "${n:0:4}-${n:4:2}-${n:6:2} ${n:9:2}:${n:11:2}:${n:13:2}" +%s 2>/dev/null || echo 0; }

[ -f "$ENV_FILE" ] || { fail "settings file $ENV_FILE exists"; done_; }
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
PROJECT="${COMPOSE_PROJECT_NAME:-construction-workspace}"

# 1. The destination is the NAS share: a network mount (with SMB encryption for CIFS) that carries the marker file.
#    An unmounted NAS leaves an empty local folder, which has no marker (RUNBOOK §10.5).
if [ -z "${OFFSITE_DIR:-}" ] || [ ! -d "$OFFSITE_DIR" ]; then fail "the off-host destination (OFFSITE_DIR) is set and reachable"; done_; fi
if [ -f "$OFFSITE_DIR/$MARKER" ]; then pass "the destination carries the share's marker"; else fail "the destination carries the share's marker ($OFFSITE_DIR/$MARKER)"; fi
if [ "${OFFSITE_MUST_BE_MOUNT:-1}" = 0 ]; then
	echo "NOTE the destination is a local stand-in (OFFSITE_MUST_BE_MOUNT=0, staging only)"
else
	mnt="$(findmnt -n -o FSTYPE,OPTIONS --target "$OFFSITE_DIR" 2>/dev/null)"
	fstype="${mnt%% *}"
	case "$fstype" in
		cifs | smb3) if grep -q 'seal' <<< "$mnt"; then pass "the destination is an encrypted SMB mount ($fstype, seal)"; else fail "the SMB mount uses encryption (add seal: RUNBOOK §10.5)"; fi ;;
		nfs | nfs4) if grep -q "sec=krb5p" <<< "$mnt"; then pass "the destination is an encrypted NFS mount (krb5p)"; else fail "the NFS mount uses encryption (sec=krb5p: RUNBOOK §10.5)"; fi ;;
		*) fail "the destination is a network mount (found: ${fstype:-not a mount})" ;;
	esac
fi
DEST="$OFFSITE_DIR/${SITE_NAME:?}"

# 2. The newest local set is there, its checksums verify there, and they are the local set's checksums.
latest="$(ls -1d "${BACKUP_DIR:?}"/20* 2>/dev/null | sort | tail -1)"
[ -n "$latest" ] || { fail "a local backup set exists"; done_; }
name="$(basename "$latest")"
if [ -d "$DEST/$name" ] && (cd "$DEST/$name" && sha256sum -c --quiet SHA256SUMS >/dev/null 2>&1) \
		&& cmp -s "$DEST/$name/SHA256SUMS" "$latest/SHA256SUMS"; then
	pass "the newest set ($name) is on the share, verified against the local set's checksums"
else
	fail "the newest set ($name) is on the share, verified against the local set's checksums"
fi

# 3. The last copy is recorded as OK for that set, within the last 26 hours.
status="$BACKUP_DIR/offsite-status.txt"
st="$(sed -n 's/^STATUS //p' "$status" 2>/dev/null)"; sset="$(sed -n 's/^SET //p' "$status" 2>/dev/null)"
sdate="$(sed -n 's/^DATE //p' "$status" 2>/dev/null)"
age=$(( $(date +%s) - $(date -d "${sdate:-1970-01-01}" +%s 2>/dev/null || echo 0) ))
if [ "$st" = OK ] && [ "$sset" = "$name" ] && [ "$age" -lt $((26 * 3600)) ]; then
	pass "the last off-host copy is recorded OK for $name"
else
	fail "the last off-host copy is recorded OK for $name (status ${st:-none}, set ${sset:-none}, age ${age}s)"
fi

# 4. Retention, against the Desk setting: nothing older than keep_days (+1) beyond the minimum of 7 sets, and every
#    local set from the window is also on the share (pruning removed nothing it should have kept).
B=(docker compose -p "$PROJECT" exec -T backend)
cfg="$(MSYS_NO_PATHCONV=1 "${B[@]}" bench --site "$SITE_NAME" execute construction_core.backups.offsite_settings 2>/dev/null | grep '^{' | tail -1)"
keep="$(sed -n 's/.*"keep_days": *\([0-9]*\).*/\1/p' <<< "$cfg")"
if [ -z "$keep" ]; then
	fail "the Desk setting (Backup Settings) can be read"
else
	cutoff=$(( $(date -u +%s) - (keep + 1) * 86400 ))
	sets=(); others=""
	for d in "$DEST"/*; do
		[ -d "$d" ] || continue
		n="$(basename "$d")"
		if is_set "$n"; then sets+=("$n"); else others="$others $n"; fi
	done
	old=""
	if [ "${#sets[@]}" -gt 7 ]; then
		for n in "${sets[@]}"; do [ "$(epoch "$n")" -lt "$cutoff" ] && [ "$n" != "$name" ] && old="$old $n"; done
	fi
	if [ -z "$old" ]; then pass "no set on the share is older than the Desk setting ($keep days, at least 7 kept)"; else fail "sets older than $keep days remain:$old"; fi
	# From when copies began (the oldest set on the share), or the window, whichever is later.
	since="$cutoff"
	if [ "${#sets[@]}" -gt 0 ]; then
		first="$(printf '%s\n' "${sets[@]}" | sort | head -1)"
		[ "$(epoch "$first")" -gt "$since" ] && since="$(epoch "$first")"
	fi
	missing=""
	for l in "$BACKUP_DIR"/20*; do
		n="$(basename "$l")"; is_set "$n" || continue
		[ "$(epoch "$n")" -ge "$since" ] && [ ! -d "$DEST/$n" ] && missing="$missing $n"
	done
	if [ -z "$missing" ]; then pass "every local set since copies began (within $keep days) is also on the share"; else fail "local sets missing on the share:$missing"; fi
	[ -z "$others" ] || echo "NOTE folders on the share that are not sets (left alone):$others"
fi

# 5. Desk shows the same result.
desk="$(MSYS_NO_PATHCONV=1 "${B[@]}" bench --site "$SITE_NAME" execute frappe.db.get_single_value --args '["Backup Settings", "last_offsite_status"]' 2>/dev/null | tail -1)"
desk_set="$(MSYS_NO_PATHCONV=1 "${B[@]}" bench --site "$SITE_NAME" execute frappe.db.get_single_value --args '["Backup Settings", "last_offsite_set"]' 2>/dev/null | tail -1)"
if [ "$desk" = OK ] && [ "$desk_set" = "$name" ]; then pass "Desk (Backup Settings) shows the last copy: OK, $name"; else fail "Desk shows the last copy (status ${desk:-none}, set ${desk_set:-none})"; fi

done_
