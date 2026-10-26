#!/usr/bin/env bash
# P3-10: what a guest (no session) gets from a deployed stack, black-box over HTTPS: every public page answers what it
# should and nothing else, no answer carries a traceback or a person's or project's data, and each page carries its
# Permissions-Policy (discussion §3.6, approvals §4.7). Run by deploy/check-routes.sh; prints PASS/FAIL lines and exits 1
# on any failure. Settings: the env file of check-staging.sh (SITE_NAME, HTTPS_PORT, CA_FILE, COMPOSE_PROJECT_NAME,
# CHECK_USER, CHECK_CLIENT); the check project "Staging check" is made by deploy/seed-check.sh.
set -uo pipefail
unset MSYS_NO_PATHCONV  # curl is a native program on Windows and needs its paths converted
ENV_FILE="${CW_ENV_FILE:-$HOME/.construction-workspace/staging/staging.env}"
command -v cygpath >/dev/null 2>&1 && ENV_FILE="$(cygpath -m "$ENV_FILE")"
fails=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; fails=$((fails + 1)); }
[ -f "$ENV_FILE" ] || { fail "settings file $ENV_FILE exists"; echo "FAILED: $fails failure(s)"; exit 1; }
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
HTTPS_PORT="${HTTPS_PORT:-443}"
PROJECT="${COMPOSE_PROJECT_NAME:-construction-workspace}"
BASE="https://$SITE_NAME$([ "$HTTPS_PORT" = 443 ] || echo ":$HTTPS_PORT")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
CURL=(curl -sS --max-time 30 --resolve "$SITE_NAME:$HTTPS_PORT:127.0.0.1")
[ -n "${CA_FILE:-}" ] && CURL+=(--cacert "$CA_FILE")  # verified TLS always; never -k
[ -n "${CA_FILE:-}" ] && curl -V | grep -qi schannel && CURL+=(--ssl-no-revoke)
# Markers of private data: the check accounts and the check project. None may appear in any guest answer.
MARKERS=("${CHECK_USER:-staging-check@example.com}" "${CHECK_CLIENT:-staging-client@example.com}" "Staging check")

# probe <path> <expect>: expect is "page" (200), "login" (a redirect to a sign-in page), "refused" (403, 404, or a
# redirect to /404) or "stock" (Frappe's own data-free page, 200). Every body: no traceback, no marker.
probe() {
	local path="$1" want="$2" r code to ok=0 m
	r="$("${CURL[@]}" -D "$TMP/h" -o "$TMP/b" -w '%{http_code} %{redirect_url}' "$BASE$path")"
	code="${r%% *}"; to="${r#* }"
	case "$want" in
		page | stock) [ "$code" = 200 ] && ok=1 ;;
		login) case "$code $to" in 30[12]\ "$BASE"/login* | 30[12]\ "$BASE"/portal/login* | 30[12]\ "$BASE"/desk) ok=1 ;; esac ;;
		refused) case "$code $to" in 403\ * | 404\ * | 30[12]\ "$BASE"/404) ok=1 ;; esac ;;
	esac
	[ "$ok" = 1 ] && pass "guest $path answers $want ($code${to:+ $to})" || fail "guest $path answers $want (got: $r)"
	if grep -q 'Traceback (most recent call last)' "$TMP/b"; then fail "guest $path shows no traceback"; fi
	for m in "${MARKERS[@]}"; do grep -qiF "$m" "$TMP/b" && fail "guest $path carries no private data (found: $m)"; done
	return 0
}

# Our public pages: the sign-in pages, the join page, the receipt's dispute page, the evidence mailbox's confirmation.
for p in / /login /portal/login /update-password /join /approval-dispute /evidence-mailbox /api/method/ping; do probe "$p" page; done
# The app's areas send a guest to sign in.
for p in /workspace /portal /desk /app "/workspace/x/discuss" "/portal/x"; do probe "$p" login; done
# Frappe's other pages and the data APIs refuse a guest (the web forms that write account data are off, D-197).
for p in /me /contact /about /blog /list /search /third_party_apps /unsubscribe /qrcode /newsletters /rss /manifest.json \
	/edit-profile /request-data /request-to-delete-data /update-profile /files/x.html /private/files/x.pdf \
	/api/resource/User /api/resource/Construction%20Project /api/resource/File /api/resource/Discuss%20Message \
	/api/resource/Approval%20Event /api/method/frappe.auth.get_logged_user "/join/a/b"; do probe "$p" refused; done
# Frappe's own pages that answer a guest with no data in them: a message page, the error page, the print view's
# "parameters required", sign-up's page (sign-up itself is off, D-197), the site script, robots, the sitemap, OAuth's
# discovery document. Listed so a new page answering a guest is seen.
for p in /message /error /printview /complete_signup /website_script.js /robots.txt /sitemap.xml /.well-known/openid-configuration; do
	probe "$p" stock
done
# An unhandled error answers a guest without a traceback (D-241): Frappe's token sign-in with no token raises one.
"${CURL[@]}" -o "$TMP/b" "$BASE/api/method/frappe.www.login.login_via_token"
[ -s "$TMP/b" ] && ! grep -q 'Traceback' "$TMP/b" && pass "an unhandled error shows a guest no traceback ($(head -c 80 "$TMP/b"))" || fail "an unhandled error shows a guest no traceback"

# Permissions-Policy: exactly one header per answer, with the policy of the page.
APP="camera=(), microphone=(self), geolocation=()"
PORTAL="camera=(), microphone=(self), geolocation=(self)"
NONE="camera=(), microphone=(), geolocation=()"
policy() {  # policy <path> <wanted>
	local got
	"${CURL[@]}" -D "$TMP/h" -o /dev/null "$BASE$1"
	got="$(grep -i '^permissions-policy:' "$TMP/h" | tr -d '\r' | cut -d' ' -f2-)"
	[ "$got" = "$2" ] && pass "$1 sends Permissions-Policy: $2" || fail "$1 sends one Permissions-Policy: $2 (got: ${got:-none})"
}
VENDOR=/home/frappe/frappe-bench/sites/assets/construction_core/vendor
dirs="$(MSYS_NO_PATHCONV=1 docker compose -p "$PROJECT" exec -T frontend sh -c "cd $VENDOR && ls -d cadviewer-* opencadstudio-* pdfjs-*" 2>/dev/null | tr -d '\r')"
policy /login "$APP"
policy /join "$APP"
policy /portal/login "$PORTAL"
policy /office/web-apps/apps/api/documents/api.js "$NONE"
for d in $dirs; do
	case "$d" in pdfjs-*) f=pdf.worker.min.js ;; *) f=index.html ;; esac
	policy "/assets/construction_core/vendor/$d/$f" "$NONE"
done
[ "$(wc -w <<< "$dirs")" -ge 3 ] && pass "the vendored viewers were found ($(tr '\n' ' ' <<< "$dirs"))" || fail "the vendored viewers were found (got: $dirs)"

[ "$fails" -eq 0 ] && echo "OK: 0 failure(s)" || echo "FAILED: $fails failure(s)"
[ "$fails" -eq 0 ]
