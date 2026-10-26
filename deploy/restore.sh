#!/usr/bin/env bash
# Restore a backup set made by deploy/backup.sh (P1-19). Run on the host.
#
#   CW_ENV_FILE=stack.env bash deploy/restore.sh --drill <set-dir>
#       Restores into a throwaway stack (compose project "<project>-drill", no published ports), verifies it and
#       removes it again. Writes the result to <BACKUP_DIR>/restore-drill.txt (deploy/check-staging.sh reads it).
#   CW_ENV_FILE=stack.env bash deploy/restore.sh --into-live <set-dir> [--confirm-overwrite]
#       Disaster recovery into the stack named by the env file (RUNBOOK.md §6). On a new server (no site yet) it
#       just restores. Over an existing site it refuses unless --confirm-overwrite is given; it then takes a safety
#       backup first and stops the app services while it restores.
# Either mode takes --heads <file>: the JSON list of {project, seq, hash} saved from the last daily digest mail
# (its heads.json attachment, kept outside the server). The restored chain is then verified against those heads
# (approvals.verify.run, P3-81); the drill fails if a head is missing or any check fails.
#
# Nothing is restored unless the set is intact: its checksums match and every part, including the encryption
# key, is present. Verified after a restore: a staff login (CHECK_USER/CHECK_PASSWORD); every file's bytes, public
# and private, against the content hash recorded in the database; the frozen approval copies (approvals.tar, P3-76),
# restored beside the private files (as frappe, never through a link), each file's SHA-256 equal to its name and the
# count equal to the archive's, and every copy the database's Approval Requests name present and matching its name; the
# Document Server's data, restored into its volume and counted; templates rendering with restricted globals (the
# configurator's disable_render_safe_exec set to the integer 0).
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep container paths as written
cd "$(dirname "$0")"

usage="usage: restore.sh --drill|--into-live <set-dir> [--confirm-overwrite] [--heads <file>]"
MODE="${1:?$usage}"
SET="$(cd "${2:?$usage}" && pwd)"
shift 2
CONFIRM="" HEADS=""
while [ $# -gt 0 ]; do
	case "$1" in
		--confirm-overwrite) CONFIRM=--confirm-overwrite ;;
		--heads) [ -f "${2:-}" ] || { echo "$usage" >&2; exit 2; }; HEADS="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift ;;
		*) echo "$usage" >&2; exit 2 ;;
	esac
	shift
done
MOUNT="$SET"
HEADS_MOUNT="$HEADS"
if command -v cygpath >/dev/null 2>&1; then  # Docker Desktop wants C:/...
	MOUNT="$(cygpath -m "$SET")"; [ -z "$HEADS" ] || HEADS_MOUNT="$(cygpath -m "$HEADS")"
fi
ENV_FILE="${CW_ENV_FILE:?set CW_ENV_FILE to the env file of the stack}"
command -v cygpath >/dev/null 2>&1 && ENV_FILE="$(cygpath -m "$ENV_FILE")"  # docker.exe reads C:/... paths
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
: "${SITE_NAME:?}" "${DB_ROOT_PASSWORD:?}" "${CHECK_USER:?}" "${CHECK_PASSWORD:?}" "${BACKUP_DIR:?}" "${APP_IMAGE:?}"
LIVE="${COMPOSE_PROJECT_NAME:-construction-workspace}"
BACKUP_DIR_HOST="$BACKUP_DIR"  # the drill report goes next to the live backups

report=()
ok=1
note() { report+=("$1"); echo "$1"; case "$1" in FAIL*) ok=0 ;; esac; }
refuse() { echo "REFUSED: $1" >&2; echo "RESULT FAIL (nothing was restored)"; exit 1; }

# 1. The set must be intact before anything is touched.
(cd "$SET" && sha256sum -c --quiet SHA256SUMS >/dev/null 2>&1) || refuse "the set's checksums do not match"
part() { ls "$SET"/$1 2>/dev/null | grep -v "${2:-^$}" | head -1; }
sql=$(part "*-database.sql.gz"); pub=$(part "*-files.tar" private-files); priv=$(part "*-private-files.tar")
conf=$(part "*-site_config_backup.json"); office="$SET/office-data.tar.gz"
for f in "$sql" "$pub" "$priv" "$conf" "$office"; do [ -n "$f" ] && [ -s "$f" ] || refuse "the set is missing a part (${f:-?})"; done
key="$(sed -n 's/.*"encryption_key": *"\([^"]*\)".*/\1/p' "$conf")"
[ -n "$key" ] || refuse "the set's site config has no encryption key"
sql=$(basename "$sql"); pub=$(basename "$pub"); priv=$(basename "$priv")
appr="$SET/approvals.tar"  # absent from a set made before P3-76
[ ! -e "$appr" ] || [ -s "$appr" ] || refuse "the set's approvals archive is empty"
note "PASS the set is intact (checksums, every part, the encryption key)"

case "$MODE" in
	--drill) PROJECT="$LIVE-drill" ;;
	--into-live) PROJECT="$LIVE" ;;
	*) echo "$usage" >&2; exit 2 ;;
esac
C=(docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yml --profile office)
APP_SERVICES=(backend websocket queue-short queue-long scheduler backup frontend documentserver)

if [ "$MODE" = --drill ]; then
	# The drill stack publishes nothing (the proxy is not started) and keeps its own volumes and backup folder.
	DRILL_BACKUPS="$(mktemp -d)"
	export BACKUP_DIR="$DRILL_BACKUPS"
	trap '"${C[@]}" down -v --remove-orphans >/dev/null 2>&1; rm -rf "$DRILL_BACKUPS"' EXIT
	"${C[@]}" up -d db redis-cache redis-queue configurator >/dev/null
	for _ in $(seq 1 100); do
		st=$("${C[@]}" ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' | awk '$1=="configurator"{print $2, $3}')
		[ "$st" = "exited 0" ] && break
		sleep 3
	done
	[ "$st" = "exited 0" ] || refuse "the drill's configurator did not finish: $st"
else
	# Present or absent must be a clear answer: a failed docker run is not "no site".
	site=$("${C[@]}" run --rm -T backend bash -c 'test -d "sites/'"$SITE_NAME"'" && echo SITE=PRESENT || echo SITE=ABSENT' 2>/dev/null | grep -o 'SITE=[A-Z]*' | tail -1)
	case "$site" in
		SITE=PRESENT)
			[ "$CONFIRM" = --confirm-overwrite ] || refuse "site $SITE_NAME exists; add --confirm-overwrite to replace it"
			echo ">> safety backup of the current site first"
			"${C[@]}" exec -T backup bash /usr/local/bin/cw-backup.sh || refuse "the safety backup failed"
			;;
		SITE=ABSENT) ;;
		*) refuse "could not tell whether site $SITE_NAME exists (is the stack's image and database up?)" ;;
	esac
	"${C[@]}" stop "${APP_SERVICES[@]}" >/dev/null 2>&1 || true
fi

# 2. Restore: an empty site first when there is none (its throwaway admin password is replaced by the restored
# database), then the database and both file archives, then the encryption key; then the Document Server's data.
# The set is root-only (backup.sh): root copies it to a folder bench (as frappe) can read, then removes it.
"${C[@]}" run --rm -T --no-deps --user root -v "$MOUNT:/restore-set:ro" -e DB_ROOT_PASSWORD backend bash -c \
	'set -e; mkdir /restore && cp /restore-set/* /restore/ && chown -R frappe /restore && trap "rm -rf /restore" EXIT
	as() { runuser -u frappe -- "$@"; }
	test -d "sites/'"$SITE_NAME"'" || as bench new-site "'"$SITE_NAME"'" --mariadb-user-host-login-scope=% \
		--db-root-password "$DB_ROOT_PASSWORD" --admin-password "$(head -c 24 /dev/urandom | od -An -tx1 | tr -d " \n")" \
		>/dev/null
	as bench --site "'"$SITE_NAME"'" restore "/restore/'"$sql"'" --with-public-files "/restore/'"$pub"'" \
		--with-private-files "/restore/'"$priv"'" --db-root-password "$DB_ROOT_PASSWORD" --force' \
	&& note "PASS bench restore" || note "FAIL bench restore"
# The frozen approval copies go beside the private files (not into them: P3-76). Extracted over what is there, never
# wiped, so a restore cannot remove a copy; each file's SHA-256 must equal its name, and every file of the archive must be there.
# Nothing is written outside the folder or through a link: the archive may hold only SHA-256-named files, and a link in the
# way (a crafted private-files archive can plant one) refuses the step. Root only reads the set; frappe writes.
if [ -e "$appr" ]; then
	res=$("${C[@]}" run --rm -T --no-deps --user root -v "$MOUNT:/restore-set:ro" backend bash -s "$SITE_NAME" 2>/dev/null <<'SH' || echo error
set -e
d="sites/$1/private/cc_approvals"
refuse() { echo "APPROVALS REFUSED $1"; exit 0; }
[ ! -L "sites/$1/private" ] && [ ! -L "$d" ] || refuse "the folder is a link"
[ -z "$(find "$d" -type l 2>/dev/null)" ] || refuse "a link lies under the folder"
list=$(tar --numeric-owner -tvf /restore-set/approvals.tar) || refuse "the archive cannot be listed"
bad=$(printf '%s' "$list" | grep -Ev '^(-[^ ]+ +[0-9]+/[0-9]+ +[0-9]+ +[0-9-]+ +[0-9:]+ +[0-9a-f]{2}/[0-9a-f]{64}|d[^ ]+ +[0-9]+/[0-9]+ +[0-9]+ +[0-9-]+ +[0-9:]+ +[0-9a-f]{2}/)$' | head -1)
[ -z "$bad" ] || refuse "an entry is not a SHA-256-named file: ${bad:0:120}"
while IFS= read -r f; do  # each file in the folder its name starts with, where frozen.read looks for it
	case "$f" in */|'') ;; *) n=${f##*/}; [ "${f%%/*}" = "${n:0:2}" ] || refuse "an entry is in the wrong folder: ${f:0:80}" ;; esac
done <<< "$(tar -tf /restore-set/approvals.tar)"
runuser -u frappe -- mkdir -p "$d"
runuser -u frappe -- tar -xf - -C "$d" --no-same-owner --no-same-permissions < /restore-set/approvals.tar
want=0; got=0
while IFS= read -r f; do
	[ -n "$f" ] || continue
	want=$((want + 1))
	if [ "$(sha256sum < "$d/$f" | cut -c1-64)" = "${f##*/}" ]; then got=$((got + 1)); fi
done <<< "$(tar -tf /restore-set/approvals.tar | grep -v '/$' || true)"
echo "APPROVALS $got $want"
SH
)
	read -r _ got want <<< "$(grep -o 'APPROVALS [0-9]* [0-9]*' <<< "$res" | tail -1)"
	why=$(sed -n 's/^APPROVALS REFUSED //p' <<< "$res" | head -1)
	if [ -n "$why" ]; then note "FAIL the frozen approval copies are restored (refused: $why; nothing extracted)"
	elif [ -n "${want:-}" ] && [ "$got" = "$want" ]; then note "PASS the frozen approval copies are restored, each matching its SHA-256 name ($got files)"
	else note "FAIL the frozen approval copies are restored, each matching its SHA-256 name (${got:-?} of ${want:-?} files)"; fi
else
	note "NOTE this set has no approvals archive (made before P3-76): no frozen approval copies to restore"
fi
export CW_KEY="$key"  # by variable name: never on a command line
"${C[@]}" run --rm -T --no-deps -e CW_KEY backend bash -c \
	'bench --site "'"$SITE_NAME"'" set-config encryption_key "$CW_KEY" >/dev/null && bench --site "'"$SITE_NAME"'" migrate >/dev/null' \
	&& note "PASS encryption key restored and site migrated" || note "FAIL encryption key restored and site migrated"
expected=$(tar -tzf "$SET/office-data.tar.gz" | grep -vc '/$' || true)
restored=$(docker run --rm --user root --entrypoint bash -v "${PROJECT}_office-data:/office-data" -v "$MOUNT:/restore:ro" \
	"$APP_IMAGE" -c 'find /office-data -mindepth 1 -delete && tar -xzpf /restore/office-data.tar.gz -C /office-data && find /office-data -type f | wc -l' 2>/dev/null || echo error)
[ "$restored" = "$expected" ] && note "PASS the Document Server data is restored ($restored files)" \
	|| note "FAIL the Document Server data is restored ($restored of $expected files)"

# 3. Verify inside the restored site (credentials by variable name only).
verify=$("${C[@]}" run --rm -T --no-deps -e CHECK_USER -e CHECK_PASSWORD backend bash -c \
	'bench --site "'"$SITE_NAME"'" console' 2>&1 <<'PY'
import hashlib, json, os, re
from frappe.utils.password import check_password
try:
    check_password(os.environ["CHECK_USER"], os.environ["CHECK_PASSWORD"]); print("VERIFY PASS staff login works")
except Exception as e:
    print("VERIFY FAIL staff login works:", type(e).__name__)
rows = frappe.get_all("File", filters={"is_folder": 0}, fields=["file_url", "is_private", "content_hash"])
local = [r for r in rows if (r.file_url or "").startswith(("/files/", "/private/files/"))]
good = 0
for r in local:
    path = frappe.get_site_path("private" if r.file_url.startswith("/private/") else "public", "files", r.file_url.rsplit("/", 1)[-1])
    try: digest = hashlib.md5(open(path, "rb").read()).hexdigest()
    except OSError: digest = None
    good += bool(r.content_hash) and digest == r.content_hash
print(("VERIFY PASS" if local and good == len(local) else "VERIFY FAIL"), f"every file matches its recorded hash ({good}/{len(local)}, public and private)")
try:
    from frappe.utils.safe_exec import is_render_exec_enabled
    print("VERIFY PASS templates render with restricted globals" if is_render_exec_enabled() else "VERIFY FAIL templates render with restricted globals (disable_render_safe_exec is not the integer 0)")
except Exception as e:
    print("VERIFY FAIL the template setting could not be checked:", type(e).__name__)
# the console runs a last block only after a blank line, so one follows it
try:
    if not frappe.db.exists("DocType", "Approval Request"):
        print("VERIFY PASS no Approval Request doctype on this site (a set from before P3-76): no frozen copies to check")
    else:
        names, reqs, bad = set(), 0, 0
        for text in frappe.get_all("Approval Request", pluck="frozen_files"):
            reqs += 1
            try: names |= {e["shown_sha256"] for e in json.loads(text or "{}").values()}
            except (ValueError, KeyError, TypeError, AttributeError): bad += 1
        good = 0
        for n in names:
            try: good += bool(re.fullmatch("[0-9a-f]{64}", n)) and hashlib.sha256(open(frappe.get_site_path("private", "cc_approvals", n[:2], n), "rb").read()).hexdigest() == n
            except (OSError, TypeError): pass
        print(("VERIFY PASS" if good == len(names) and not bad else "VERIFY FAIL"), f"every frozen approval copy the requests name is on disk and matches its name ({good}/{len(names)} copies, {reqs} requests, {bad} unreadable lists)")
except Exception as e:
    print("VERIFY FAIL the frozen approval copies could not be checked:", type(e).__name__)

PY
)
while IFS= read -r line; do
	case "$line" in *"VERIFY PASS"*) note "PASS ${line#*VERIFY PASS }" ;; *"VERIFY FAIL"*) note "FAIL ${line#*VERIFY FAIL }" ;; esac
done <<< "$verify"
grep -q "VERIFY" <<< "$verify" || note "FAIL the restored site could be checked"
# A check whose line never came out did not run: that fails too (every outcome of the two last checks names its subject).
grep -q "VERIFY .*template" <<< "$verify" || note "FAIL the template setting was not checked"
grep -q "VERIFY .*frozen" <<< "$verify" || note "FAIL the frozen approval copies were not checked"

# 4. The chain against the heads mailed outside the server (approvals.verify.run, P3-81).
if [ -n "$HEADS" ]; then
	res=$("${C[@]}" run --rm -T --no-deps -v "$HEADS_MOUNT:/heads.json:ro" backend bench --site "$SITE_NAME" execute construction_core.approvals.verify.run --kwargs '{"heads": "/heads.json"}' 2>&1 | tr -d ' \n\r' || true)
	case "$res" in
		*'"ok":true'*) note "PASS the approvals chain matches the heads mailed outside the server" ;;
		*) note "FAIL the approvals chain matches the heads mailed outside the server ($(tail -c 300 <<< "$res"))" ;;
	esac
else
	note "NOTE no --heads file given: the approvals chain was not checked against outside heads"
fi

if [ "$MODE" = --drill ]; then
	{
		echo "SET $(basename "$SET")"
		echo "DATE $(date -u +%Y-%m-%dT%H:%M:%SZ)"
		printf '%s\n' "${report[@]}"
		[ "$ok" = 1 ] && echo "RESULT PASS" || echo "RESULT FAIL"
	} > "$BACKUP_DIR_HOST/restore-drill.txt"
else
	if [ "$ok" = 1 ]; then
		"${C[@]}" up -d >/dev/null && echo ">> the stack is started again; run deploy/check-staging.sh"
	else
		echo ">> the restore failed: the app services stay stopped (the safety backup, if one was taken, is the newest set)"
	fi
fi
[ "$ok" = 1 ] && echo "RESULT PASS" || { echo "RESULT FAIL"; exit 1; }
