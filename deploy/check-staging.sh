#!/usr/bin/env bash
# G-48 (P1-19): a deployed stack is ready. Black-box over HTTPS, plus `docker compose` for health and backups.
# Prints PASS/FAIL per check; exits 1 on any failure. Nothing is skipped: a missing setting is a failure.
#
# Settings come from an env file kept outside the repository (default ~/.construction-workspace/staging/staging.env):
#   SITE_NAME            the site's host name (staging: staging.localhost)
#   HTTPS_PORT, HTTP_PORT the published proxy ports (default 443, 80)
#   CA_FILE              the CA that signed the proxy's certificate (staging: the proxy's internal CA, exported by
#                        deploy/staging.sh); empty for a publicly trusted certificate
#   CHECK_USER, CHECK_PASSWORD   a staff account used only by this check
#   OFFICE_FILE          the File id of an office document in a project CHECK_USER belongs to
#   COMPOSE_PROJECT_NAME the compose project name (default construction-workspace)
#   BACKUP_DIR           where deploy/backup.sh writes (on this host)
set -uo pipefail
# Git Bash on Windows: curl is a native program and needs its paths (/dev/null, temp files) converted.
unset MSYS_NO_PATHCONV

ENV_FILE="${CW_ENV_FILE:-$HOME/.construction-workspace/staging/staging.env}"
command -v cygpath >/dev/null 2>&1 && ENV_FILE="$(cygpath -m "$ENV_FILE")"  # docker.exe reads C:/... paths
fails=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; fails=$((fails + 1)); }

if [ ! -f "$ENV_FILE" ]; then
	fail "settings file $ENV_FILE exists"
	echo "FAILED: $fails failure(s)"
	exit 1
fi
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
for v in SITE_NAME CHECK_USER CHECK_PASSWORD OFFICE_FILE BACKUP_DIR; do
	if [ -z "${!v:-}" ]; then fail "setting $v is set"; fi
done
[ "$fails" -eq 0 ] || { echo "FAILED: $fails failure(s)"; exit 1; }

HTTPS_PORT="${HTTPS_PORT:-443}"
HTTP_PORT="${HTTP_PORT:-80}"
PROJECT="${COMPOSE_PROJECT_NAME:-construction-workspace}"
BASE="https://$SITE_NAME$([ "$HTTPS_PORT" = 443 ] || echo ":$HTTPS_PORT")"
JAR="$(mktemp)"
HDRS="$(mktemp)"
trap 'rm -f "$JAR" "$HDRS"' EXIT
CURL=(curl -sS --max-time 30 --resolve "$SITE_NAME:$HTTPS_PORT:127.0.0.1" --resolve "$SITE_NAME:$HTTP_PORT:127.0.0.1")
[ -n "${CA_FILE:-}" ] && CURL+=(--cacert "$CA_FILE")  # verified TLS always; never -k
# Windows curl (Schannel) cannot check revocation for a private CA, which has no revocation list; the chain is
# still verified against CA_FILE.
[ -n "${CA_FILE:-}" ] && curl -V | grep -qi schannel && CURL+=(--ssl-no-revoke)

# 1. Plain HTTP only redirects to HTTPS.
loc="$("${CURL[@]}" -o /dev/null -w '%{http_code} %{redirect_url}' "http://$SITE_NAME:$HTTP_PORT/login")"
case "$loc" in
	30[178]\ "$BASE"/*) pass "HTTP redirects to HTTPS ($loc)" ;;
	*) fail "HTTP redirects to HTTPS (got: $loc)" ;;
esac

# 2. HTTPS answers with a verified certificate, HSTS and the app.
body="$("${CURL[@]}" -D "$HDRS" "$BASE/api/method/ping" 2>&1)"
headers="$(cat "$HDRS")"
if echo "$body" | grep -q '"pong"'; then pass "HTTPS ping answers pong (verified TLS)"; else fail "HTTPS ping answers pong: $(echo "$body" | head -c 300)"; fi
if echo "$headers" | grep -qi '^strict-transport-security: *max-age=[1-9]'; then pass "HSTS is sent"; else fail "HSTS is sent"; fi

# 3. Only the proxy is reachable from outside, on exactly its two ports, and the proxy reaches only frontend.
published="$(docker compose -p "$PROJECT" ps --format '{{.Service}} {{.Ports}}' 2>&1 | grep -- '->')"
others="$(grep -v '^proxy ' <<< "$published")"
proxy_ports="$(grep -o '[0-9]*->' <<< "$published" | sort -u | tr '\n' ' ')"
if [ -z "$others" ] && [ "$proxy_ports" = "$(printf '%s->\n' "$HTTPS_PORT" "$HTTP_PORT" | sort -u | tr '\n' ' ')" ]; then
	pass "only proxy publishes ports ($proxy_ports)"
else
	fail "only proxy publishes ports (published: $(tr '\n' ';' <<< "$published"))"
fi
# A TCP connect test (nc -z): it fails only when nothing answers, whatever the protocol behind the port.
reach() { MSYS_NO_PATHCONV=1 docker compose -p "$PROJECT" exec -T proxy nc -z -w 2 "$1" "$2" >/dev/null 2>&1; }
if reach frontend 8080; then
	pass "the proxy reaches frontend:8080 (the probe works)"
	for target in backend:8000 websocket:9000 db:3306 redis-queue:6379 redis-cache:6379 documentserver:80 clamav:3310; do
		if reach "${target%:*}" "${target#*:}"; then fail "the proxy cannot reach $target"; else pass "the proxy cannot reach $target"; fi
	done
else
	fail "the proxy reaches frontend:8080 (the probe itself is broken)"
fi
code="$("${CURL[@]}" -o /dev/null -w '%{http_code}' -H "Host: evil.example" "http://127.0.0.1:$HTTP_PORT/x")"
if [ "$code" = 404 ]; then pass "plain HTTP for another host is not found"; else fail "plain HTTP for another host is not found (HTTP $code)"; fi

# 4. Login sets a Secure, HttpOnly session cookie (Frappe sees the request as HTTPS).
# The password goes to curl on stdin (printf is a shell builtin), never on its command line, where any local user could
# read it from the process list (P2-07 exit audit).
login="$(printf '%s' "$CHECK_PASSWORD" | "${CURL[@]}" -D - -o /dev/null -c "$JAR" -X POST "$BASE/api/method/login" \
	--data-urlencode "usr=$CHECK_USER" --data-urlencode "pwd@-")"
sid_line="$(echo "$login" | grep -i '^set-cookie: *sid=' | head -1)"
if [ -n "$sid_line" ] && ! echo "$sid_line" | grep -qi 'sid=Guest'; then pass "login succeeds"; else fail "login succeeds"; fi
if echo "$sid_line" | grep -qi 'secure' && echo "$sid_line" | grep -qi 'httponly'; then
	pass "the session cookie is Secure and HttpOnly"
else
	fail "the session cookie is Secure and HttpOnly ($sid_line)"
fi

# 5. Setup is complete (no setup wizard on first login): Desk's boot data says so.
desk="$("${CURL[@]}" -L -b "$JAR" "$BASE/app")"
if grep -q '"setup_complete":true' <<< "$desk"; then pass "setup is complete"; else fail "setup is complete"; fi

# 6. Browser modules are served as JavaScript.
for path in /assets/construction_core/vendor/pdfjs-4.10.38/pdf.worker.min.js /office/web-apps/apps/api/documents/api.js; do
	ct="$("${CURL[@]}" -o /dev/null -w '%{http_code} %{content_type}' "$BASE$path")"
	case "$ct" in
		"200 application/javascript"* | "200 text/javascript"*) pass "$path is served as JavaScript" ;;
		*) fail "$path is served as JavaScript (got: $ct)" ;;
	esac
done

# 7. Realtime authenticates a signed-in user (a handshake alone succeeds even when authentication is broken).
eio="$BASE/socket.io/?EIO=4&transport=polling"
open="$("${CURL[@]}" -b "$JAR" -H "Origin: $BASE" "$eio")"
sid="$(echo "$open" | sed -n 's/.*"sid":"\([^"]*\)".*/\1/p')"
if [ -z "$sid" ]; then
	fail "realtime handshake ($(echo "$open" | head -c 120))"
else
	"${CURL[@]}" -b "$JAR" -H "Origin: $BASE" -H "Content-Type: text/plain;charset=UTF-8" --data "40/$SITE_NAME," "$eio&sid=$sid" >/dev/null
	reply=""
	for _ in 1 2 3 4 5; do
		reply="$reply$("${CURL[@]}" -b "$JAR" -H "Origin: $BASE" "$eio&sid=$sid")"
		case "$reply" in *"40/$SITE_NAME,{"* | *"44/$SITE_NAME"*) break ;; esac
	done
	case "$reply" in
		*"40/$SITE_NAME,{"*) pass "realtime authenticates the signed-in user" ;;
		*) fail "realtime authenticates the signed-in user ($(echo "$reply" | head -c 200))" ;;
	esac
fi
foreign="$("${CURL[@]}" -o /dev/null -w '%{http_code}' -H "Origin: https://evil.example" "$eio")"
if [ "$foreign" = 403 ]; then pass "realtime refuses a foreign Origin"; else fail "realtime refuses a foreign Origin (HTTP $foreign)"; fi

# 8. Office editing is configured: the editor gets a signed ONLYOFFICE configuration, not the download fallback.
csrf="$(echo "$desk" | sed -n 's/.*csrf_token = "\([^"]*\)".*/\1/p' | head -1)"
[ -n "$csrf" ] && pass "Desk issues a CSRF token" || fail "Desk issues a CSRF token"
cfg="$("${CURL[@]}" -b "$JAR" -H "X-Frappe-CSRF-Token: $csrf" -X POST \
	--data-urlencode "file=$OFFICE_FILE" "$BASE/api/method/construction_core.office.api.editor_config")"
if echo "$cfg" | grep -q '"documentType"' && echo "$cfg" | grep -q '"token"' && echo "$cfg" | grep -q "\"callbackUrl\":\"http://frontend:8080/"; then
	pass "office editing returns a signed configuration with an internal callback"
else
	fail "office editing returns a signed configuration with an internal callback ($(echo "$cfg" | head -c 200))"
fi

# 9. Every service is up, and those with a health check are healthy.
ps="$(docker compose -p "$PROJECT" ps --format '{{.Service}} {{.State}} {{.Health}}' 2>&1)"
for svc in proxy frontend backend websocket queue-short queue-long scheduler db documentserver backup clamav clamav-update; do
	line="$(echo "$ps" | grep "^$svc ")"
	case "$line" in
		"$svc running healthy" | "$svc running ") pass "service $svc is up ($line)" ;;
		*) fail "service $svc is running and healthy (got: ${line:-absent})" ;;
	esac
done

# 9a. Templates render with restricted globals (P3-76): the configurator's disable_render_safe_exec is the integer 0. bench
# execute prints nothing for a falsy result, so anything but exactly "true" fails.
render="$(docker compose -p "$PROJECT" exec -T backend bench --site "$SITE_NAME" execute frappe.utils.safe_exec.is_render_exec_enabled 2>/dev/null | tail -1)"
if [ "$render" = true ]; then pass "templates render with restricted globals"; else fail "templates render with restricted globals (disable_render_safe_exec is not the integer 0; got: ${render:-nothing})"; fi

# 10. Backups: a complete, readable set from the last 26 hours; a restore drill in the last 35 days that passed on a
# set still kept (RUNBOOK: monthly, and after every upgrade).
latest="$(ls -1d "$BACKUP_DIR"/20* 2>/dev/null | sort | tail -1)"
if [ -z "$latest" ]; then
	fail "a backup set exists in $BACKUP_DIR"
else
	age=$(( $(date +%s) - $(date -r "$latest" +%s) ))
	if [ "$age" -lt $((26 * 3600)) ]; then pass "the latest backup set is recent ($(basename "$latest"))"; else fail "the latest backup set is recent (age ${age}s)"; fi
	for part in "*-database.sql.gz" "*-files.tar" "*-private-files.tar" "*-site_config_backup.json" "approvals.tar" "office-data.tar.gz" "SHA256SUMS"; do
		f="$(compgen -G "$latest/$part" | grep -v "$( [ "$part" = "*-files.tar" ] && echo private-files || echo '^$')" | head -1)"
		case "$part" in
			*.sql.gz | *.tar.gz) [ -s "$f" ] && gzip -t "$f" 2>/dev/null ;;
			*.tar) [ -s "$f" ] && tar --force-local -tf "$f" >/dev/null 2>&1 ;;  # --force-local: "C:/..." is not a remote host
			*.json) [ -s "$f" ] && grep -q '"encryption_key"' "$f" ;;
			*) [ -s "$f" ] ;;
		esac && pass "the backup set has a readable $part" || fail "the backup set has a readable $part"
	done
	if (cd "$latest" && sha256sum -c --quiet SHA256SUMS >/dev/null 2>&1); then pass "the backup set matches its checksums"; else fail "the backup set matches its checksums"; fi
	drill="$BACKUP_DIR/restore-drill.txt"
	dset="$(sed -n 's/^SET //p' "$drill" 2>/dev/null)"
	ddate="$(sed -n 's/^DATE //p' "$drill" 2>/dev/null)"
	dage=$(( $(date +%s) - $(date -d "$ddate" +%s 2>/dev/null || echo 0) ))
	if [ -f "$drill" ] && grep -q '^RESULT PASS' "$drill" && [ -n "$dset" ] && [ -d "$BACKUP_DIR/$dset" ] && [ "$dage" -lt $((35 * 86400)) ]; then
		pass "a restore drill passed in the last 35 days on a kept set (SET $dset, $ddate)"
	else
		fail "a restore drill passed in the last 35 days on a kept set ($drill: SET ${dset:-?}, DATE ${ddate:-?})"
	fi
fi


# 12. The virus scanner (P3-07, D-159): clamd answers the backend, its signatures are at most two days old, it finds the
# standard test file and passes clean bytes, and it cannot reach the internet. The test string is put together at run
# time from two halves, so no file on this host holds it (a desktop antivirus would quarantine this script).
scan_out="$(MSYS_NO_PATHCONV=1 docker compose -p "$PROJECT" exec -T backend /home/frappe/frappe-bench/env/bin/python - <<'PY' 2>&1
import datetime, socket, struct
NUL = b"\0"
def talk(payload):
	with socket.create_connection(("clamav", 3310), timeout=30) as s:
		s.sendall(payload)
		reply = b""
		while not reply.endswith(NUL):
			got = s.recv(4096)
			if not got:
				break
			reply += got
		return reply.rstrip(NUL).decode()
def scan(data):
	return talk(b"zINSTREAM" + NUL + struct.pack("!I", len(data)) + data + struct.pack("!I", 0))
print("PING", talk(b"zPING" + NUL))
version = talk(b"zVERSION" + NUL)
stamp = datetime.datetime.strptime(version.split("/")[-1].strip(), "%a %b %d %H:%M:%S %Y")
print("AGE", (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - stamp).days, version)
print("TEST", scan(("X5O!P%@AP[4" + chr(92) + "PZX54(P^)7CC)7}$EI" + "CAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*").encode()))
print("CLEAN", scan(bytes(1024)))
PY
)"
grep -q '^PING PONG$' <<< "$scan_out" && pass "clamd answers the backend" || fail "clamd answers the backend ($(head -c 200 <<< "$scan_out"))"
age="$(sed -n 's/^AGE \([0-9-]*\) .*/\1/p' <<< "$scan_out")"
if [ -n "$age" ] && [ "$age" -le 2 ]; then pass "the virus signatures are at most two days old ($(sed -n 's/^AGE [0-9-]* //p' <<< "$scan_out"))"; else fail "the virus signatures are at most two days old (${age:-unknown} days)"; fi
grep -q '^TEST stream: .*FOUND$' <<< "$scan_out" && pass "clamd finds the standard test file" || fail "clamd finds the standard test file"
grep -q '^CLEAN stream: OK$' <<< "$scan_out" && pass "clamd passes clean bytes" || fail "clamd passes clean bytes"
if MSYS_NO_PATHCONV=1 docker compose -p "$PROJECT" exec -T clamav nc -z -w 3 database.clamav.net 443 >/dev/null 2>&1; then
	fail "clamd cannot reach the internet"
else
	pass "clamd cannot reach the internet"
fi

if [ "$fails" -eq 0 ]; then echo "OK: 0 failure(s)"; else echo "FAILED: $fails failure(s)"; fi
[ "$fails" -eq 0 ]
