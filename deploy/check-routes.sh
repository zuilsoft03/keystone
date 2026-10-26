#!/usr/bin/env bash
# P2-07: the route findings of ARCHITECTURE §3.2 re-checked on a deployed stack (the delivery image), black-box over
# HTTPS, with both portal presenters (D-121). Prints PASS/FAIL per check; exits 1 on any failure.
#
# Settings: the same env file as deploy/check-staging.sh, plus a check client made by `deploy/staging.sh up`:
#   SITE_NAME, HTTPS_PORT, CA_FILE, COMPOSE_PROJECT_NAME
#   CHECK_USER, CHECK_PASSWORD              the staff check account
#   CHECK_CLIENT, CHECK_CLIENT_PASSWORD     a client contact of the "Staging check" project
# The portal is checked under the presenter the site uses now. With BOTH_PRESENTERS=1 (as `deploy/staging.sh routes`
# sets it) the check also switches `cc_portal_spa` to the other presenter for about two minutes, then puts back the
# value it found, an interrupted run included. On a live site run that only before go-live or in a maintenance window.
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
for v in SITE_NAME CHECK_USER CHECK_PASSWORD CHECK_CLIENT CHECK_CLIENT_PASSWORD; do
	[ -n "${!v:-}" ] || fail "setting $v is set"
done
[ "$fails" -eq 0 ] || { echo "FAILED: $fails failure(s)"; exit 1; }

HTTPS_PORT="${HTTPS_PORT:-443}"
PROJECT="${COMPOSE_PROJECT_NAME:-construction-workspace}"
BASE="https://$SITE_NAME$([ "$HTTPS_PORT" = 443 ] || echo ":$HTTPS_PORT")"
TMP="$(mktemp -d)"
# The presenter the site uses now: the value of cc_portal_spa in its site config, or `absent` (the app presenter).
ORIGINAL="$(MSYS_NO_PATHCONV=1 docker compose -p "$PROJECT" exec -T backend python3 -c \
	"import json; print(json.load(open('sites/$SITE_NAME/site_config.json')).get('cc_portal_spa', 'absent'))" 2>/dev/null | tr -d '\r')"
# A switch is undone on every exit, an interrupted run included, back to the value found (P2-07 exit audit).
restore_presenter() {
	local back='"None"'  # update_site_config removes the key for "None"
	[ "$ORIGINAL" != absent ] && back="$ORIGINAL"
	MSYS_NO_PATHCONV=1 docker compose -p "$PROJECT" exec -T backend bench --site "$SITE_NAME" \
		execute frappe.installer.update_site_config --args "[\"cc_portal_spa\", $back]" >/dev/null 2>&1 || true
}
SWITCHED=0
trap '[ "$SWITCHED" = 1 ] && restore_presenter; rm -rf "$TMP"' EXIT
trap 'exit 130' INT TERM
CURL=(curl -sS --max-time 30 --resolve "$SITE_NAME:$HTTPS_PORT:127.0.0.1")
[ -n "${CA_FILE:-}" ] && CURL+=(--cacert "$CA_FILE")  # verified TLS always; never -k
[ -n "${CA_FILE:-}" ] && curl -V | grep -qi schannel && CURL+=(--ssl-no-revoke)

# get <jar|-> <path> <out>: writes the body to <out>, prints "<code> <redirect>".
get() {
	local jar=() ; [ "$1" != - ] && jar=(-b "$TMP/$1" -c "$TMP/$1")
	"${CURL[@]}" "${jar[@]}" -o "$3" -w '%{http_code} %{redirect_url}' "$BASE$2"
}
login() {  # login <jar> <user> <password>: the password goes to curl on stdin, never on its command line
	printf '%s' "$3" | "${CURL[@]}" -c "$TMP/$1" -o "$TMP/$1.login" -w '%{http_code}' --data-urlencode "usr=$2" --data-urlencode "pwd@-" "$BASE/api/method/login"
}
bench() { MSYS_NO_PATHCONV=1 docker compose -p "$PROJECT" exec -T backend bench --site "$SITE_NAME" "$@" >/dev/null 2>&1; }

[ "$(login staff "$CHECK_USER" "$CHECK_PASSWORD")" = 200 ] && pass "the staff check account signs in" || fail "the staff check account signs in"
[ "$(login client "$CHECK_CLIENT" "$CHECK_CLIENT_PASSWORD")" = 200 ] && pass "the check client signs in" || fail "the check client signs in"
"${CURL[@]}" -b "$TMP/staff" -o "$TMP/proj.json" -G "$BASE/api/resource/Construction%20Project" \
	--data-urlencode 'filters=[["project_name","=","Staging check"]]'
PRJ="$(grep -o '"name":"[^"]*"' "$TMP/proj.json" | head -1 | cut -d'"' -f4)"
[ -n "$PRJ" ] && pass "the check project is $PRJ" || fail "the check project is found"

# 1. /workspace: a Guest goes to login.
r="$(get - /workspace "$TMP/b")"
case "$r" in 30[12]\ *login*) pass "Guest /workspace goes to login ($r)" ;; *) fail "Guest /workspace goes to login (got: $r)" ;; esac

# 2. An unknown /workspace shape ends in our own 404, the same bytes for every requester (D-109): never Frappe's 500.
UNKNOWN="/workspace/a/b/c/d/e/f"
r1="$(get - "$UNKNOWN" "$TMP/u-guest")"; r2="$(get staff "$UNKNOWN" "$TMP/u-staff")"; r3="$(get client "$UNKNOWN" "$TMP/u-client")"
if [ "${r1%% *}" = 404 ] && [ "${r2%% *}" = 404 ] && [ "${r3%% *}" = 404 ] && grep -q "Page not found" "$TMP/u-guest"; then
	pass "unknown /workspace shape is our 404 for Guest, staff and client"
else
	fail "unknown /workspace shape is our 404 (guest $r1, staff $r2, client $r3)"
fi
if cmp -s "$TMP/u-guest" "$TMP/u-staff" && cmp -s "$TMP/u-guest" "$TMP/u-client"; then pass "that 404 is the same bytes for everyone"; else fail "that 404 is the same bytes for everyone"; fi

# 3. Staff get the app at /workspace and on a deep path; its script is served.
r="$(get staff /workspace "$TMP/ws")"
if [ "${r%% *}" = 200 ] && grep -q 'window.cc_boot' "$TMP/ws"; then pass "staff /workspace is the app"; else fail "staff /workspace is the app (got: $r)"; fi
script="$(grep -o 'src="/assets/construction_shell/shell/[^"]*\.js"' "$TMP/ws" | head -1 | cut -d'"' -f2)"
r="$(get - "$script" "$TMP/js")"
[ -n "$script" ] && [ "${r%% *}" = 200 ] && pass "the app's script is served ($script)" || fail "the app's script is served ($script: $r)"
r="$(get staff "/workspace/$PRJ/discuss" "$TMP/deep")"
if [ "${r%% *}" = 200 ] && grep -q 'window.cc_boot' "$TMP/deep"; then pass "staff deep path /workspace/$PRJ/discuss is the app"; else fail "staff deep path is the app (got: $r)"; fi
# A project that does not exist is the app's own not-found view (200), so nothing is cached as a 404 (D-054).
r="$(get staff /workspace/NO-SUCH-PROJECT/home "$TMP/nsp")"
[ "${r%% *}" = 200 ] && pass "an unknown project is the app (its own not-found view)" || fail "an unknown project is the app (got: $r)"

# 4. A client is refused in the page body and gets no app.
r="$(get client /workspace "$TMP/wc")"
if [ "${r%% *}" = 403 ] && grep -q "This area is for the project team" "$TMP/wc" && ! grep -q 'window.cc_boot' "$TMP/wc"; then
	pass "a client at /workspace gets the 403 body, no app"
else
	fail "a client at /workspace gets the 403 body (got: $r)"
fi

# 5. /portal: a Guest goes to login; another project and an unknown shape are the same 404 for the client.
r="$(get - /portal "$TMP/pg")"
case "$r" in 30[12]\ *login*) pass "Guest /portal goes to login ($r)" ;; *) fail "Guest /portal goes to login (got: $r)" ;; esac
case "$r" in 30[12]\ */portal/login*) pass "Guest /portal goes to the clients' sign-in" ;; *) fail "Guest /portal goes to the clients' sign-in (got: $r)" ;; esac
r="$(get - /portal/login "$TMP/plogin")"  # P3-26 (D-265): LoginB, a page of its own, not the portal's guest redirect
[ "${r%% *}" = 200 ] && pass "Guest /portal/login is the clients' sign-in" || fail "Guest /portal/login is the clients' sign-in (got: $r)"
r1="$(get client /portal/NO-SUCH-PROJECT "$TMP/p404a")"; r2="$(get client /portal/a/b/c/d/e "$TMP/p404b")"
[ "${r1%% *}" = 404 ] && [ "${r2%% *}" = 404 ] && pass "the client gets 404 for a foreign project and an unknown shape" \
	|| fail "the client gets 404 for a foreign project and an unknown shape ($r1, $r2)"

# 5a. /join (P3-17, D-214): the sign-in-free join page answers a Guest, carries no invitation data and claims its
# namespace: anything below it is our own 404 (DR-3).
r="$(get - /join "$TMP/join")"
[ "${r%% *}" = 200 ] && ! grep -q "$PRJ" "$TMP/join" && pass "Guest /join is the join page, with no project in it" 	|| fail "Guest /join is the join page, with no project in it (got: $r)"
r="$(get - /join/a/b "$TMP/join404")"
[ "${r%% *}" = 404 ] && pass "a path below /join is our 404" || fail "a path below /join is our 404 (got: $r)"
# 5b. /approval-dispute (P3-78, approvals §3.7): a receipt's "This was not me" page answers a Guest with no request data;
# its token stays in the link's fragment, so the page itself records nothing.
r="$(get - /approval-dispute "$TMP/dispute")"
[ "${r%% *}" = 200 ] && ! grep -q "$PRJ" "$TMP/dispute" && pass "Guest /approval-dispute is the dispute page, with no project in it" \
	|| fail "Guest /approval-dispute is the dispute page, with no project in it (got: $r)"

# 6. Both presenters (D-121): the portal app, then the server-rendered portal, for the same client and project.
# Frappe caches site config per worker for 60 s (frappe/config.py, site_cache ttl=60): a switch shows within a minute.
presenter() {  # presenter <label> <expect_app 1|0>
	local label="$1" app="$2" r i has
	for i in $(seq 1 30); do
		r="$(get client "/portal/$PRJ" "$TMP/pp")"
		has=0; grep -q 'window.cc_boot' "$TMP/pp" && has=1
		[ "${r%% *}" = 200 ] && [ "$has" = "$app" ] && break
		sleep 3
	done
	if [ "${r%% *}" != 200 ]; then fail "$label: the client's project answers 200 (got: $r)"; return; fi
	if [ "$app" = 1 ]; then
		grep -q 'window.cc_boot' "$TMP/pp" && grep -q '/assets/construction_shell/shell/' "$TMP/pp" \
			&& pass "$label: /portal/$PRJ is the portal app" || fail "$label: /portal/$PRJ is the portal app"
	else
		! grep -q 'window.cc_boot' "$TMP/pp" && grep -q "Staging check" "$TMP/pp" \
			&& pass "$label: /portal/$PRJ is the server-rendered portal" || fail "$label: /portal/$PRJ is the server-rendered portal"
	fi
}
case "$ORIGINAL" in absent | 1 | True | true) NOW=1 ;; *) NOW=0 ;; esac  # cint(cc_portal_spa), as ws_portal.py reads it
[ -n "$ORIGINAL" ] && pass "the site's presenter is read (cc_portal_spa: $ORIGINAL)" || fail "the site's presenter is read"
label() { [ "$1" = 1 ] && echo "the app presenter" || echo "the server presenter"; }
presenter "$(label "$NOW") (as the site has it)" "$NOW"
if [ "${BOTH_PRESENTERS:-0}" = 1 ]; then
	OTHER=$((1 - NOW))
	SWITCHED=1
	if bench set-config cc_portal_spa "$OTHER"; then
		presenter "$(label "$OTHER") (switched for this check)" "$OTHER"
		r="$(get client /portal/a/b/c/d/e "$TMP/p404c")"
		[ "${r%% *}" = 404 ] && pass "$(label "$OTHER"): an unknown shape is still 404" || fail "$(label "$OTHER"): unknown shape 404 (got: $r)"
	else
		fail "cc_portal_spa can be set"
	fi
	restore_presenter
	SWITCHED=0
	presenter "$(label "$NOW") again (the value put back)" "$NOW"
else
	echo "(the other presenter was not switched in: set BOTH_PRESENTERS=1 to check it too)"
fi

# 6a. P3-10: Allowed File Extensions applies to every upload in a request. Staff upload a .csv (accepted, then deleted)
# and an .html (refused).
csrf="$("${CURL[@]}" -b "$TMP/staff" -L "$BASE/desk" | sed -n 's/.*csrf_token = "\([^"]*\)".*/\1/p' | head -1)"
printf 'a,b\n' > "$TMP/probe.csv"; printf '<b>x</b>' > "$TMP/probe.html"
up() {  # cygpath: Windows curl cannot read a /tmp path inside -F
	local p="$TMP/$1"; command -v cygpath >/dev/null 2>&1 && p="$(cygpath -m "$p")"
	"${CURL[@]}" -b "$TMP/staff" -H "X-Frappe-CSRF-Token: $csrf" -F "file=@$p;filename=golive-probe.${1#*.}" -F is_private=1 "$BASE/api/method/upload_file"
}
fid="$(up probe.csv | grep -o '"name":"[0-9a-z]*"' | head -1 | cut -d'"' -f4)"
if [ -n "$fid" ]; then
	pass "staff may upload a .csv"
	"${CURL[@]}" -b "$TMP/staff" -H "X-Frappe-CSRF-Token: $csrf" -X DELETE -o /dev/null "$BASE/api/resource/File/$fid"
else
	fail "staff may upload a .csv"
fi
up probe.html | grep -q FileTypeNotAllowed && pass "an .html upload is refused (Allowed File Extensions)" || fail "an .html upload is refused (Allowed File Extensions)"

# 7. P3-10: what a guest gets from every public page, and the Permissions-Policy of each (deploy/check-public.sh).
while IFS= read -r line; do
	case "$line" in PASS*) pass "public: ${line#PASS }" ;; FAIL*) fail "public: ${line#FAIL }" ;; esac
done < <(CW_ENV_FILE="$ENV_FILE" bash "$(dirname "$0")/check-public.sh" 2>&1)

echo
[ "$fails" -eq 0 ] && { echo "OK: 0 failure(s)"; exit 0; } || { echo "FAILED: $fails failure(s)"; exit 1; }
