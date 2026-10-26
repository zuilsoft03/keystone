#!/usr/bin/env bash
# One backup set (P1-19), run by the `backup` service of deploy/compose.yml. It runs as root, because the Document
# Server's data is readable only by root; bench itself runs as the frappe user. It writes:
#   <stamp>-<site>-database.sql.gz, -files.tar, -private-files.tar, -site_config_backup.json  (bench backup)
#   approvals.tar        the frozen approval copies, <site>/private/cc_approvals/<aa>/<sha256> (P3-76; outside private/files)
#   office-data.tar.gz   the Document Server's data volume (mounted read-only)
#   SHA256SUMS           checksums of the above; deploy/check-staging.sh and deploy/restore.sh verify them
# The site config holds the encryption key and the database password, and the files are client data: every set is
# private (folder 700, files 600).
#
# Off-host copies (P2-01, D-103, D-107): each new set is then copied to the destination mounted at /offsite (the NAS
# share, OFFSITE_DIR in the stack's settings file), checked against its checksums there, and only then renamed into
# a set; sets older than the Desk setting "Keep copies for (days)" are removed there, never the newest. The result
# goes to Backup Settings (Desk) and to <BACKUP_DIR>/offsite-status.txt. A failed copy never touches the local sets.
# Destinations are functions copy_to_<kind>; `path` (a mounted folder) is the first kind. The share must carry the
# marker file .cw-offsite-target; sets go to <share>/<site>/; the NAS never keeps fewer than OFFSITE_MIN_SETS (7).
#
#   cw-backup.sh          one set now, then its off-host copy
#   cw-backup.sh --copy <set>   copy one existing set off the host again (after a failed copy)
#   cw-backup.sh --loop   one set now, then one every BACKUP_EVERY_HOURS hours; keeps the newest BACKUP_KEEP sets
#
# A set is published (renamed from .partial-*) only when every part exists and reads back; only then are older
# sets pruned. A failed run leaves the existing sets alone. (Each step is checked explicitly: bash ignores `set -e`
# inside a function called from `if` or `||`.)
set -euo pipefail
umask 077

SITE="${SITE_NAME:?set SITE_NAME}"
OUT="${BACKUP_OUT:-/backups}"
KEEP="${BACKUP_KEEP:-14}"
EVERY="${BACKUP_EVERY_HOURS:-24}"
BENCH="${BENCH_DIR:-/home/frappe/frappe-bench}"
case "$KEEP" in '' | *[!0-9]* | 0) echo "BACKUP_KEEP must be a whole number of at least 1" >&2; exit 2 ;; esac
MARKER=".cw-offsite-target"  # on the NAS share only (RUNBOOK §10.5); proves /offsite is the share
MIN_SETS="${OFFSITE_MIN_SETS:-7}"  # the NAS never keeps fewer sets than this, whatever the dates say
case "$MIN_SETS" in '' | *[!0-9]* | 0) echo "OFFSITE_MIN_SETS must be a whole number of at least 1" >&2; exit 2 ;; esac
AS_FRAPPE=()
[ "$(id -u)" = 0 ] && AS_FRAPPE=(runuser -u frappe --)

one_set() {
	local stamp dir work f appr left
	stamp="$(date -u +%Y%m%dT%H%M%SZ)"
	dir="$OUT/.partial-$stamp"
	mkdir -p "$dir" || return 1
	chmod 700 "$OUT" "$dir" || return 1
	# bench (as frappe) writes into its own private folder; root then moves the files into the root-only set.
	work="$(mktemp -d)" || return 1
	if [ "$(id -u)" = 0 ]; then chown frappe "$work" || return 1; fi
	(cd "$BENCH" && "${AS_FRAPPE[@]}" bench --site "$SITE" backup --with-files --backup-path "$work") \
		&& mv "$work"/* "$dir"/ && rmdir "$work" || { rm -rf "$work"; return 1; }
	# A frozen copy is written before the row that names it, so taking them after the dump covers every row in it. Only
	# files named by a SHA-256 go in, each in the folder of its name's first two characters (the \1: restore.sh refuses the
	# whole archive for any other entry, so one stray file would lose every copy); an unfinished temporary file is not a
	# copy; no folder yet is an empty archive.
	appr="$BENCH/sites/$SITE/private/cc_approvals"
	if [ -d "$appr" ]; then
		find "$appr" -mindepth 2 -maxdepth 2 -type f -regextype posix-extended -regex '.*/([0-9a-f]{2})/\1[0-9a-f]{62}' -printf '%P\0' \
			| tar -cf "$dir/approvals.tar" -C "$appr" --null -T - || return 1
		left=$(( $(find "$appr" -type f | wc -l) - $(tar -tf "$dir/approvals.tar" | wc -l) ))  # never silent
		[ "$left" -le 0 ] || echo "approvals: $left file(s) not named by a SHA-256 in the folder of its first two characters were left out of approvals.tar" >&2
	else
		tar -cf "$dir/approvals.tar" -T /dev/null || return 1
	fi
	if [ -d /office-data ]; then
		tar -czf "$dir/office-data.tar.gz" -C /office-data . || return 1
	fi
	# Every part must exist, be non-empty and read back.
	f=$(ls "$dir"/*-database.sql.gz 2>/dev/null | head -1); [ -s "$f" ] && gzip -t "$f" || { echo "no valid database dump" >&2; return 1; }
	f=$(ls "$dir"/*-private-files.tar 2>/dev/null | head -1); [ -s "$f" ] && tar -tf "$f" >/dev/null || { echo "no valid private files archive" >&2; return 1; }
	f=$(ls "$dir"/*-files.tar 2>/dev/null | grep -v private-files | head -1); [ -s "$f" ] && tar -tf "$f" >/dev/null || { echo "no valid public files archive" >&2; return 1; }
	f=$(ls "$dir"/*-site_config_backup.json 2>/dev/null | head -1); [ -s "$f" ] && grep -q '"encryption_key"' "$f" || { echo "no site config with the encryption key" >&2; return 1; }
	[ -s "$dir/approvals.tar" ] && tar -tf "$dir/approvals.tar" >/dev/null || { echo "no valid approvals archive" >&2; return 1; }
	if [ -d /office-data ]; then tar -tzf "$dir/office-data.tar.gz" >/dev/null || return 1; fi
	(cd "$dir" && sha256sum -- * > SHA256SUMS) || return 1
	chmod 600 "$dir"/* || return 1
	mv "$dir" "$OUT/$stamp" || return 1  # a set appears complete or not at all
	LAST_SET="$OUT/$stamp"
	echo "backup set $OUT/$stamp"
	# Keep the newest $KEEP sets; partial folders of a failed run are removed after a day.
	ls -1d "$OUT"/20* 2>/dev/null | sort | head -n -"$KEEP" | xargs -r rm -rf --
	find "$OUT" -maxdepth 1 -name '.partial-*' -mmin +1440 -exec rm -rf -- {} +
}

# --- off-host copies ---------------------------------------------------------------------------------------------

site_call() {  # bench execute as frappe; prints the last JSON line it returns
	(cd "$BENCH" && "${AS_FRAPPE[@]}" bench --site "$SITE" execute "construction_core.backups.$1" ${2:+--kwargs "$2"}) 2>/dev/null \
		| grep '^{' | tail -1
}

set_epoch() {  # 20261010T073606Z -> seconds since 1970 (UTC); nothing for a name that is not a set's
	local n="$1"
	[[ "$n" =~ ^20[0-9]{6}T[0-9]{6}Z$ ]] || return 0
	date -u -d "${n:0:4}-${n:4:2}-${n:6:2} ${n:9:2}:${n:11:2}:${n:13:2}" +%s 2>/dev/null
}

kwargs() {  # <status> <set> <message> -> a Python literal for `bench execute --kwargs` (which eval()s it): repr()
	python3 -c 'import sys; print(repr({"status": sys.argv[1], "set_name": sys.argv[2], "message": sys.argv[3][:300]}))' "$@"
}

real_sets() {  # <folder> -> the sets in it, oldest first (names that only look like sets do not count)
	ls -1 "$1" 2>/dev/null | grep -E '^20[0-9]{6}T[0-9]{6}Z$' | sort
}

copy_to_path() {  # <set dir> <destination root> <keep days>
	# The destination root must prove it is the share (P2-01 audit 1): an unmounted NAS leaves an empty local folder,
	# and a copy there would never leave the host. The marker file is created once, on the share itself (RUNBOOK §10.5).
	local set="$1" root="$2" keep="$3" dest stamp part old newest d e m cutoff count
	[ -f "$root/$MARKER" ] || { echo "the destination $root has no $MARKER: the NAS share is not mounted there" >&2; return 1; }
	dest="$root/$SITE"  # one folder per site: two stacks sharing a NAS never prune each other's sets
	mkdir -p "$dest" && [ -w "$dest" ] || { echo "the destination $dest is not a writable folder" >&2; return 1; }
	stamp="$(basename "$set")"
	part="$dest/.partial-$stamp"
	old="$dest/.replaced-$stamp"
	rm -rf -- "$part"
	# A copy moved aside by an earlier re-copy that could not be put back is the only copy of that set: restore it.
	if [ -e "$old" ]; then
		if [ -e "$dest/$stamp" ]; then rm -rf -- "$old"; else mv -- "$old" "$dest/$stamp" || return 1; fi
	fi
	# No ownership or modes from the source (an SMB share without unix extensions refuses them); the mount decides.
	cp -r --preserve=timestamps -- "$set" "$part" || { rm -rf -- "$part"; return 1; }
	sync
	(cd "$part" && sha256sum -c --quiet SHA256SUMS && cmp -s SHA256SUMS "$set/SHA256SUMS") \
		|| { echo "the copy does not match its checksums" >&2; rm -rf -- "$part"; return 1; }
	# A re-copy of the same set: the verified copy there is moved aside first, removed only once the new one is in.
	if [ -e "$dest/$stamp" ]; then mv -- "$dest/$stamp" "$old" || return 1; fi
	if ! mv -- "$part" "$dest/$stamp"; then
		[ -e "$old" ] && mv -- "$old" "$dest/$stamp"
		return 1
	fi
	rm -rf -- "$old"
	chmod 700 "$dest/$stamp" 2>/dev/null || true
	# Prune: a set goes only when both the date in its name and its folder's time are older than <keep> days, and
	# never below OFFSITE_MIN_SETS sets: a wrong clock, or a folder named for the future, cannot empty the history.
	cutoff=$(( $(date -u +%s) - keep * 86400 ))
	count="$(real_sets "$dest" | wc -l)"
	newest="$dest/$stamp"
	for n in $(real_sets "$dest"); do
		d="$dest/$n"
		[ "$count" -gt "$MIN_SETS" ] || break
		[ -d "$d" ] && [ "$d" != "$newest" ] || continue
		e="$(set_epoch "$n")"
		m="$(stat -c %Y "$d" 2>/dev/null || echo 0)"
		if [ -n "$e" ] && [ "$e" -lt "$cutoff" ] && [ "$m" -lt "$cutoff" ]; then
			rm -rf -- "$d" && count=$((count - 1))
		fi
	done
	find "$dest" -maxdepth 1 -name '.partial-*' -mmin +1440 -exec rm -rf -- {} +
	# A .replaced-<set> is the only copy of <set> while <set> is missing: put it back; once <set> exists, remove it.
	for d in "$dest"/.replaced-*; do
		[ -e "$d" ] || continue
		if [ -e "$dest/${d##*/.replaced-}" ]; then rm -rf -- "$d"; else mv -- "$d" "$dest/${d##*/.replaced-}"; fi
	done
	return 0
}

offsite() {  # copy LAST_SET off the host, and record the result in Desk and in offsite-status.txt
	local cfg enabled keep status msg
	cfg="$(site_call offsite_settings)"
	enabled="$(python3 -c 'import json,sys; print(int(json.loads(sys.argv[1] or "{}").get("enabled", 1)))' "$cfg" 2>/dev/null || echo 1)"
	keep="$(python3 -c 'import json,sys; print(int(json.loads(sys.argv[1] or "{}").get("keep_days", 30)))' "$cfg" 2>/dev/null || echo 30)"
	[ "$keep" -ge 1 ] 2>/dev/null || keep=30
	if [ "$enabled" != 1 ]; then
		status="DISABLED"; msg="off-host copies are switched off in Backup Settings"
	elif [ ! -d /offsite ]; then
		status="FAILED"; msg="no off-host destination is configured (OFFSITE_DIR)"
	elif msg="$(copy_to_path "$LAST_SET" /offsite "$keep" 2>&1)"; then
		status="OK"; msg="copied and verified; keeping $keep days"
	else
		status="FAILED"; msg="${msg:-the copy failed}"
	fi
	# One line, at most 300 characters (not bytes: a cut UTF-8 character would not reach Desk); quotes are safe,
	# kwargs() uses repr().
	msg="$(python3 -c 'import sys; print(" ".join(sys.argv[1].split())[:300])' "$msg")"
	# The last-copy record is about the newest set: a re-copy of an older set (--copy) only reports its result.
	if [ "$(basename "$LAST_SET")" != "$(real_sets "$OUT" | tail -1)" ]; then
		echo "off-host copy of the older set $(basename "$LAST_SET"): $status ($msg)"
		[ "$status" != FAILED ]
		return
	fi
	printf 'STATUS %s\nSET %s\nDATE %s\nMESSAGE %s\n' "$status" "$(basename "$LAST_SET")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$msg" \
		> "$OUT/offsite-status.txt"
	(cd "$BENCH" && "${AS_FRAPPE[@]}" bench --site "$SITE" execute construction_core.backups.record_offsite \
		--kwargs "$(kwargs "$status" "$(basename "$LAST_SET")" "$msg")") >/dev/null 2>&1 \
		|| echo "could not record the off-host result in Desk (offsite-status.txt has it)" >&2
	echo "off-host copy: $status ($msg)"
	[ "$status" != FAILED ]
}

run_once() {  # 2: no new set; 3: a new set, but its off-host copy failed
	one_set || { echo "backup failed; existing sets kept" >&2; return 2; }
	offsite || { echo "the off-host copy failed; the local set is kept" >&2; return 3; }
}

[ "${CW_BACKUP_LIB:-}" = 1 ] && return 0 2>/dev/null  # sourced by deploy/test-scripts.sh for its function tests

if [ "${1:-}" = "--copy" ]; then  # re-copy one existing set off the host (RUNBOOK §5), without making a new one
	n="${2:?usage: cw-backup.sh --copy <set>}"
	[[ "$n" =~ ^20[0-9]{6}T[0-9]{6}Z$ ]] && [ -d "$OUT/$n" ] || { echo "no backup set $OUT/$n" >&2; exit 2; }
	LAST_SET="$OUT/$n"
	offsite || exit 3
	exit 0
fi

if [ "${1:-}" = "--loop" ]; then
	until [ -f "$BENCH/sites/$SITE/site_config.json" ]; do sleep 60; done  # the site is created after first start
	while true; do
		run_once || echo "retrying at the next interval" >&2
		sleep "$((EVERY * 3600))"
	done
else
	rc=0
	run_once || rc=$?
	[ "$rc" = 2 ] && exit 1  # exit 1: no new set (as before); exit 3: a new set, but no off-host copy
	exit "$rc"
fi
