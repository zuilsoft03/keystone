#!/usr/bin/env bash
# P3-10 (D-156, D-199, D-218, D-222, D-229, D-241, D-345, D-431): a live site is set for go-live. Run on the host of the
# stack, after deploy/check-staging.sh passes; RUNBOOK §12 says what each FAIL means. Prints PASS/FAIL per assertion and
# exits 1 on any FAIL. It changes nothing but one failed sign-in of an address that does not exist (the forged-header
# probe), which the site logs.
#
#   CW_ENV_FILE=/path/to/stack.env bash deploy/check-golive.sh
#
# Settings: the env file of check-staging.sh (SITE_NAME, HTTPS_PORT, HTTP_PORT, COMPOSE_PROJECT_NAME), plus
#   TIME_REFERENCE   an HTTPS address whose Date header is the reference clock (default https://www.cloudflare.com)
# The verdict functions below take their input as arguments, so deploy/test-golive.sh can feed them bad input.
set -uo pipefail
unset MSYS_NO_PATHCONV  # curl is a native program on Windows and needs its paths converted

ENV_FILE="${CW_ENV_FILE:-$HOME/.construction-workspace/staging/staging.env}"
command -v cygpath >/dev/null 2>&1 && ENV_FILE="$(cygpath -m "$ENV_FILE")"
fails=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; fails=$((fails + 1)); }

# ports_verdict <"service ports" lines> <https port> <http port>: only the proxy publishes, exactly its two ports.
ports_verdict() {
	local others proxy_ports
	others="$(grep -- '->' <<< "$1" | grep -v '^proxy ')"
	proxy_ports="$(grep '^proxy ' <<< "$1" | grep -o '[0-9]*->' | sort -u | tr '\n' ' ')"
	if [ -z "$others" ] && [ "$proxy_ports" = "$(printf '%s->\n' "$2" "$3" | sort -u | tr '\n' ' ')" ]; then
		pass "the proxy is the only way in: it alone publishes ports ($proxy_ports)"
	else
		fail "the proxy is the only way in: it alone publishes ports (published: $(grep -- '->' <<< "$1" | tr '\n' ';'))"
	fi
}
# edge_verdict <container names, one a line> <compose project>: the edge network holds the proxy and frontend only. A name
# that is not this project's (another stack's, or one added by hand) stays as it is, so it fails the compare.
edge_verdict() {
	local members
	members="$(printf '%s\n' "$1" | sed '/^$/d' | sed "s/^${2}-\(.*\)-[0-9]*$/\1/" | sort | tr '\n' ' ')"
	[ "$members" = "frontend proxy " ] && pass "the edge network holds the proxy and frontend only" \
		|| fail "the edge network holds the proxy and frontend only (members: ${members:-none})"
}
# realip_verdict <nginx set_real_ip_from lines> <edge subnet>: nginx believes X-Forwarded-For from the edge network only.
realip_verdict() {
	local from
	from="$(grep -o 'set_real_ip_from[[:space:]]*[^;]*' <<< "$1" | awk '{print $2}' | sort -u | tr '\n' ' ')"
	if [ -n "$2" ] && [ "$from" = "$2 " ] && [ "$2" != 0.0.0.0/0 ]; then
		pass "nginx trusts X-Forwarded-For from the edge network only ($2)"
	else
		fail "nginx trusts X-Forwarded-For from the edge network only (trusted: ${from:-none}; edge: ${2:-unknown})"
	fi
}
# clock_verdict <offset seconds or empty> <ntp: yes|no|absent>: the clock is right and kept right (approvals §4.7).
clock_verdict() {
	local off="${1#-}"
	if [ -z "$1" ]; then fail "the server clock matches the reference clock (no reference time: is the internet line up?)"
	elif [ "$off" -le 5 ]; then pass "the server clock matches the reference clock (offset $1 s)"
	else fail "the server clock matches the reference clock (offset $1 s, more than 5)"; fi
	case "$2" in
		yes) pass "the host keeps its time synchronised (timedatectl: NTPSynchronized=yes)" ;;
		absent) pass "the host keeps its time synchronised (no timedatectl on this host: the reference offset above stands for it)" ;;
		*) fail "the host keeps its time synchronised (timedatectl: NTPSynchronized=$2; enable systemd-timesyncd or chrony)" ;;
	esac
}
[ "${GOLIVE_VERDICTS_ONLY:-0}" = 1 ] && return 0 2>/dev/null  # test-golive.sh sources the functions only

if [ ! -f "$ENV_FILE" ]; then fail "settings file $ENV_FILE exists"; echo "FAILED: $fails failure(s)"; exit 1; fi
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
[ -n "${SITE_NAME:-}" ] || { fail "setting SITE_NAME is set"; echo "FAILED: $fails failure(s)"; exit 1; }
HTTPS_PORT="${HTTPS_PORT:-443}"
HTTP_PORT="${HTTP_PORT:-80}"
PROJECT="${COMPOSE_PROJECT_NAME:-construction-workspace}"
BASE="https://$SITE_NAME$([ "$HTTPS_PORT" = 443 ] || echo ":$HTTPS_PORT")"
DC=(docker compose -p "$PROJECT")
dx() { MSYS_NO_PATHCONV=1 "${DC[@]}" exec -T "$@"; }

# 1. The network: ports, nginx's trusted range, the edge network's members, and a forged header from inside.
ports_verdict "$("${DC[@]}" ps --format '{{.Service}} {{.Ports}}' 2>&1)" "$HTTPS_PORT" "$HTTP_PORT"
edge="$(docker network inspect "${PROJECT}_edge" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)"
realip_verdict "$(dx frontend cat /etc/nginx/conf.d/frappe.conf 2>/dev/null | grep set_real_ip_from)" "$edge"
edge_verdict "$(docker network inspect "${PROJECT}_edge" --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null \
	| tr ' ' '\n')" "$PROJECT"
FORGED_IP="198.51.100.$((RANDOM % 250 + 1))"  # TEST-NET-2: never a real client
FORGED_USER="golive-probe-$RANDOM$RANDOM@example.invalid"
if [ -n "$("${DC[@]}" ps -q documentserver 2>/dev/null)" ]; then
	direct="$(dx documentserver curl -s -o /dev/null -w '%{http_code}' --max-time 5 -H "X-Forwarded-For: $FORGED_IP" \
		-H "X-Frappe-Site-Name: $SITE_NAME" http://backend:8000/api/method/ping 2>/dev/null)"
	[ "${direct:-000}" = 000 ] && pass "the Document Server's container cannot reach backend:8000 (a forged X-Forwarded-For has no door)" \
		|| fail "the Document Server's container cannot reach backend:8000 with a forged X-Forwarded-For (HTTP $direct)"
	# Through nginx: a failed sign-in with a forged header; the site must log the container's own address (checked below).
	dx documentserver curl -s -o /dev/null --max-time 10 -H "X-Forwarded-For: $FORGED_IP" -H "Host: $SITE_NAME" \
		--data-urlencode "usr=$FORGED_USER" --data-urlencode "pwd=not-a-password" http://frontend:8080/api/method/login >/dev/null 2>&1
else
	fail "the forged-header probe runs from the Document Server's container (documentserver is not running)"
fi

# 2. The services: the scheduler runs; no mail catcher in the stack; the backend is not Frappe's development server.
services="$("${DC[@]}" ps --format '{{.Service}} {{.State}}' 2>&1)"
grep -q '^scheduler running' <<< "$services" && pass "the scheduler service is running" || fail "the scheduler service is running"
grep -qi '^mailpit' <<< "$services" && fail "no mail catcher runs in the stack (mailpit)" || pass "no mail catcher runs in the stack"
[ -z "$(dx backend printenv DEV_SERVER 2>/dev/null)" ] && pass "the backend is not Frappe's development server (no DEV_SERVER)" \
	|| fail "the backend is not Frappe's development server (DEV_SERVER is set)"

# 3. The site's settings, read in one console: a line per assertion. A missing line is a FAIL (the check did not run).
NAMES="pins two-step session-expiry scheduler mail-account mail-confirmed always-bcc allow-tests social-login
tracebacks setup-finished company-name privacy-contact time-zone host-name file-extensions approvals-daily-job
approvals-flag approvals-verify forged-header"
sleep 2  # the probe's Activity Log row is written after its answer
out="$(dx -e BASE="$BASE" -e FORGED_IP="$FORGED_IP" -e FORGED_USER="$FORGED_USER" backend bash -c \
	'f=$(mktemp); cat > "$f"; echo "exec(open(\"$f\").read(), {\"frappe\": frappe})" | bench --site '"$SITE_NAME"' console; rm -f "$f"' \
	2>&1 <<'PY'
# Run as one file in its own namespace: the console's functions would not see each other.
import os
from frappe.utils import cint, validate_email_address

def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"the check could not run: {type(e).__name__}: {e}"
    print("GOLIVE", "OK" if ok else "BAD", name, str(detail).replace("\n", " ")[:300])

def single(dt, field):
    return frappe.db.get_singles_dict(dt).get(field)  # straight from the table: a change in another process shows

def pins():
    from construction_core.accounts import settings
    d = settings.deviations()
    return not d, ", ".join(d) or "the D-197 sign-in settings hold"

def two_step():
    from construction_core.accounts import two_step
    d = two_step.deviations()
    return not d, ", ".join(d) or "on, OTP app, only the opt-in and required roles flagged"

def expiry():
    from construction_core.accounts.sessions import SESSION_EXPIRY
    v = single("System Settings", "session_expiry")
    return v == SESSION_EXPIRY, f"{v} (wanted {SESSION_EXPIRY})"

def scheduler():
    bad = [k for k in ("disable_scheduler", "pause_scheduler") if cint(frappe.conf.get(k))]
    if not cint(single("System Settings", "enable_scheduler")):
        bad.append("System Settings.enable_scheduler is off")
    return not bad, ", ".join(bad) or "enabled"

def account():
    name = frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1})
    return frappe.get_doc("Email Account", name) if name else None

def mail_account():
    from construction_core.accounts.mail_setup import STACK_NAMES
    acc = account()
    if not acc:
        return False, "no default outgoing Email Account (RUNBOOK §4a)"
    hosts = [h for h in (acc.smtp_server, frappe.conf.get("mail_server")) if h]
    bad = [h for h in hosts if "." not in h or h.split(".")[0].lower() in STACK_NAMES or "mailpit" in h.lower()]
    return not bad, f"{acc.name} via {acc.smtp_server}" if not bad else f"a mail catcher or stack host: {', '.join(bad)}"

def confirmed():
    acc = account()
    if not acc:
        return False, "no default outgoing Email Account"
    ok = frappe.db.get_global("cc_mail_confirmed") == f"{acc.name}|{acc.modified}"
    return ok, "confirmed by its code and unchanged since" if ok else "changed after its code was confirmed, or never confirmed (Mail settings)"

def bcc():
    rows = frappe.get_all("Email Account", filters={"enable_outgoing": 1, "always_bcc": ["is", "set"]}, pluck="name")
    return not rows, ", ".join(rows) or "none"

def social():
    rows = frappe.get_all("Social Login Key", filters={"enable_social_login": 1}, pluck="name")
    return not rows, ", ".join(rows) or "none enabled"

def tracebacks():
    bad = []
    if cint(single("System Settings", "allow_error_traceback")):
        bad.append("System Settings.allow_error_traceback")
    if cint(frappe.conf.get("developer_mode")):
        bad.append("developer_mode")
    return not bad, ", ".join(bad) or "hidden"

def finished():
    from construction_core.accounts import setup
    return setup.finished(), "finished" if setup.finished() else "the set-up wizard is not finished (/workspace as a System Manager)"

def company():
    from construction_core.onboarding.mail import brand
    return bool(brand()), brand() or "neither the Brand page nor cc_company_name names the firm"

def privacy():
    from construction_core.onboarding.privacy import contact
    c = contact()
    return bool(c) and validate_email_address(c) == c, c or "neither Firm Settings nor cc_privacy_email has one"

def zone():
    z = single("System Settings", "time_zone")
    return bool(z), z or "unset"

def host():
    v = frappe.conf.get("host_name") or ""
    return v == os.environ["BASE"], f"{v or 'unset'} (wanted {os.environ['BASE']})"

def extensions():
    from construction_core import client_files
    from construction_core.discuss.media import KINDS
    from construction_core.office.api import EXTENSIONS
    from construction_core.providers.storage import IMAGE_TYPES
    allowed = set((single("System Settings", "allowed_file_extensions") or "").upper().split())
    if not allowed:
        return False, "Allowed File Extensions is empty: every type may be uploaded, .html and .svg included"
    runs = allowed & {"HTML", "HTM", "XHTML", "SHTML", "SVG", "SVGZ", "JS", "MJS"}
    used = {e.upper() for e in (*client_files.CLIENT_TYPES, *client_files.STAFF_ROOM_TYPES, *client_files.AUDIO_TYPES,
        *client_files.MODEL_TYPES, *IMAGE_TYPES, *KINDS, *EXTENSIONS)}
    missing = used - allowed
    if runs or missing:
        return False, (f"a browser would run: {sorted(runs)} " if runs else "") + \
            (f"the app's own types are refused: {sorted(missing)}" if missing else "")
    return True, f"{len(allowed)} types, none a browser runs, every type the app works with"

def daily_job():
    j = frappe.db.get_value("Scheduled Job Type", {"method": "construction_core.approvals.digest.daily"},
        ["name", "stopped", "frequency"], as_dict=True)
    if not j:
        return False, "construction_core.approvals.digest.daily has no Scheduled Job Type (run a migrate)"
    return not cint(j.stopped) and j.frequency.startswith("Daily"), f"{j.frequency}, {'stopped' if cint(j.stopped) else 'running'}"

def flag():
    if not frappe.conf.get("cc_approvals_enabled"):
        return True, "Portal approvals off for this site (cc_approvals_enabled unset): no evidence mailbox needed"
    ok = cint(single("Approval Settings", "evidence_mailbox_confirmed"))
    return bool(ok), "on, evidence mailbox confirmed" if ok else "on, but the evidence mailbox is not confirmed"

def verify():
    from construction_core.approvals import verify as v
    r = v.run()
    return r["ok"], f"{len(r['heads'])} chain(s) verify" if r["ok"] else str(r["problems"][:3])

def forged():
    rows = frappe.get_all("Activity Log", filters={"user": os.environ["FORGED_USER"]}, pluck="ip_address")
    if not rows:
        return False, "the probe's failed sign-in was not logged (did it reach the site?)"
    return os.environ["FORGED_IP"] not in rows, f"logged {rows[0]}, not the forged {os.environ['FORGED_IP']}" \
        if os.environ["FORGED_IP"] not in rows else f"the forged address {os.environ['FORGED_IP']} was believed"

for name, fn in (("pins", pins), ("two-step", two_step), ("session-expiry", expiry), ("scheduler", scheduler),
        ("mail-account", mail_account), ("mail-confirmed", confirmed), ("always-bcc", bcc), ("allow-tests",
        lambda: (not cint(frappe.conf.get("allow_tests")), "off" if not cint(frappe.conf.get("allow_tests")) else "on")),
        ("social-login", social), ("tracebacks", tracebacks), ("setup-finished", finished), ("company-name", company),
        ("privacy-contact", privacy), ("time-zone", zone), ("host-name", host), ("file-extensions", extensions),
        ("approvals-daily-job", daily_job), ("approvals-flag", flag), ("approvals-verify", verify), ("forged-header", forged)):
    check(name, fn)

PY
)"
for n in $NAMES; do
	line="$(grep -o -m1 "GOLIVE [A-Z]* $n .*" <<< "$out")"  # the first line follows the console prompt
	case "$line" in
		"GOLIVE OK $n "*) pass "$n: ${line#GOLIVE OK $n }" ;;
		"GOLIVE BAD $n "*) fail "$n: ${line#GOLIVE BAD $n }" ;;
		*) fail "$n: the check did not run ($(grep -m1 -i 'error' <<< "$out" | head -c 200))" ;;
	esac
done

# 4. The clock (approvals §4.7): the backend's clock against the reference's Date header, and the host's own sync.
ref="$(curl -sSI --max-time 10 "${TIME_REFERENCE:-https://www.cloudflare.com}" 2>/dev/null | tr -d '\r' | sed -n 's/^[Dd]ate: //p' | head -1)"
now="$(dx backend date -u +%s 2>/dev/null | tr -d '\r')"
offset=""
[ -n "$ref" ] && [ -n "$now" ] && offset=$(( now - $(date -u -d "$ref" +%s) ))
ntp=absent
command -v timedatectl >/dev/null 2>&1 && ntp="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)"
clock_verdict "$offset" "$ntp"

if [ "$fails" -eq 0 ]; then echo "OK: 0 failure(s)"; else echo "FAILED: $fails failure(s)"; fi
[ "$fails" -eq 0 ]
