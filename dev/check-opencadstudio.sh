#!/usr/bin/env bash
# Open CAD Studio's fence on the dev site (P3-48, D-325, D-326): the policy on its folder, the refusals, and that the
# rest of the site is unchanged; then the same for the drawing viewer's folder (P3-49, D-329). Prints PASS or FAIL per check, then "OK" or "FAILED"; exit 1 on any failure.
#
# Usage (from the repo root, ws-dev up):  bash dev/check-opencadstudio.sh [base-url]
set -uo pipefail
cd "$(dirname "$0")/.."
PORT="$(sed -n 's/^DEV_HTTP_PORT=//p' dev/.env 2>/dev/null | tail -1)"
BASE="${1:-http://localhost:${PORT:-9600}}"
DIR="apps/construction_core/construction_core/public/vendor/opencadstudio-0e4c4c3"
APP="/assets/construction_core/vendor/opencadstudio-0e4c4c3"
fails=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; fails=$((fails + 1)); }
code() { curl -s --path-as-is -o /dev/null -w '%{http_code}' "$@"; }

head="$(curl -s -D - -o /dev/null -H 'Sec-Fetch-Dest: iframe' "$BASE$APP/index.html" | tr -d '\r')"
policy="$(sed -n 's/^[Cc]ontent-[Ss]ecurity-[Pp]olicy: //p' <<< "$head")"
grep -q '^HTTP/[0-9.]* 200' <<< "$head" && pass "the program's page loads in a frame" || fail "the program's page in a frame: $(head -1 <<< "$head")"
for want in "default-src 'none'" "connect-src $BASE$APP/;" "img-src $BASE$APP/ blob:;" "worker-src $BASE$APP/ blob:;" "frame-ancestors 'self'" "form-action 'none'"; do
	[[ "$policy" == *"$want"* ]] && pass "its policy has: $want" || fail "its policy lacks: $want"
done
[[ "$policy" == *"sandbox "* && "$policy" != *"allow-popups"* ]] && pass "its policy sandboxes it without popups" || fail "its policy's sandbox"
grep -qi '^cache-control: no-cache' <<< "$head" && pass "its page revalidates (no-cache)" || fail "its page's Cache-Control"
grep -qi '^x-frame-options: SAMEORIGIN' <<< "$head" && pass "the site's own headers stay" || fail "X-Frame-Options lost on the folder"
[ "$(code -H 'Sec-Fetch-Dest: document' "$BASE$APP/index.html")" = 403 ] && pass "its page opened on its own is refused" || fail "its page opened on its own is not refused"

# A dot segment next to an encoded slash, written every way the re-audit found, is refused before any location.
for path in \
	"$APP/..%2F..%2F..%2F..%2Fapi/method/ping" \
	"$APP/..%5C..%5C..%5C..%5Capi/method/ping" \
	"$APP%2F..%2F..%2F..%2F..%2Fapi/method/ping.html" \
	"$APP%2F..%2F..%2F..%2F..%2Fapi/method/ping/" \
	"$APP%2F%2e%2e%2F%2e%2e%2F%2e%2e%2F%2e%2e%2Fapi/method/ping.html?x=1" \
	"/%61ssets/construction_core/vendor/opencadstudio-0e4c4c3/..%2F..%2F..%2F..%2Fapi/method/ping.html" \
	"/assets/construction_core/vendor/opencadstudio%2D0e4c4c3/..%2F..%2F..%2Ffrappe/images/frappe-favicon.svg" \
	"$APP/.%2e%2Fprivate/files/x.html"; do
	got="$(code "$BASE$path")"
	[ "$got" = 400 ] && pass "refused: $path" || fail "not refused ($got): $path"
done

# The rest of the site is as it was.
[ "$(code "$BASE/api/method/ping")" = 200 ] && pass "the API answers" || fail "the API"
other="$(curl -s -D - -o /dev/null "$BASE/assets/construction_core/vendor/pdfjs-4.10.38/pdf.min.js" | tr -d '\r')"
grep -q '^HTTP/[0-9.]* 200' <<< "$other" && ! grep -qi '^content-security-policy' <<< "$other" && pass "other assets carry no such policy" || fail "other assets changed"
got="$(code "$BASE/app/file/Home%2FProjects")"
[ "$got" != 400 ] && pass "an encoded slash with no dot segment still passes ($got)" || fail "an encoded slash with no dot segment is refused"

for f in videos discussions supporters; do
	[ "$(tr -d '[:space:]' < "$DIR/$f.json")" = '[]' ] && pass "$f.json is empty" || fail "$f.json is not empty"
done
[ ! -e "$DIR/sw.js" ] && ! grep -Eq '<script( type="module")?>|<style>|serviceWorker' "$DIR/index.html" && pass "no inline code and no service worker" || fail "inline code or a service worker in the page"

# The drawing viewer (P3-49, D-328, D-329): the same fence on its own folder, every policy compared whole, the wasm
# compressed, the folder matched in any case, its notices readable on their own, nothing from a CDN.
CV_DIR="apps/construction_core/construction_core/public/vendor/cadviewer-1.7.6"
CV="/assets/construction_core/vendor/cadviewer-1.7.6"
F="$BASE$CV/"
heads() { curl -s --path-as-is -D - -o /dev/null "$@" | tr -d '\r'; }
csp() { sed -n 's/^[Cc]ontent-[Ss]ecurity-[Pp]olicy: //p' <<< "$1"; }
PAGE_CSP="default-src 'none'; script-src $F 'wasm-unsafe-eval'; worker-src $F; connect-src $F; img-src $F blob: data:; font-src $F; style-src-elem $F 'unsafe-inline'; style-src-attr 'unsafe-inline'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-scripts allow-same-origin"
DWG_CSP="default-src 'none'; script-src $F 'wasm-unsafe-eval' 'unsafe-eval'; connect-src $F; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-scripts allow-same-origin"
TEXT_CSP="default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox"

head="$(heads -H 'Sec-Fetch-Dest: iframe' "$BASE$CV/index.html")"
grep -q '^HTTP/[0-9.]* 200' <<< "$head" && pass "the viewer's page loads in a frame" || fail "the viewer's page in a frame: $(head -1 <<< "$head")"
[ "$(csp "$head")" = "$PAGE_CSP" ] && pass "the viewer's page has exactly its policy (no eval, no windows, forms or downloads)" || fail "the viewer's page policy: $(csp "$head")"
grep -qi '^cache-control: no-cache' <<< "$head" && pass "the viewer's page revalidates (no-cache)" || fail "the viewer's page's Cache-Control"
grep -qi '^x-frame-options: SAMEORIGIN' <<< "$head" && pass "the site's own headers stay on the viewer's folder" || fail "X-Frame-Options lost on the viewer's folder"
[ "$(code -H 'Sec-Fetch-Dest: document' "$BASE$CV/index.html")" = 403 ] && pass "the viewer's page opened on its own is refused" || fail "the viewer's page opened on its own is not refused"
bundle="$(cd "$CV_DIR" && ls assets/index-*.js 2>/dev/null | head -1)"
for f in "$bundle" workers/mtext-renderer-worker.js workers/libredwg-web.wasm fonts/fonts.json fonts/LiberationSans-Regular.ttf; do
	h="$(heads "$BASE$CV/$f")"
	[ -n "$f" ] && grep -q '^HTTP/[0-9.]* 200' <<< "$h" && [ "$(csp "$h")" = "$PAGE_CSP" ] && pass "$f is served with the page's policy" || fail "$f: $(head -1 <<< "$h"), policy $(csp "$h")"
done
h="$(heads "$BASE$CV/workers/libredwg-parser-worker.js")"
grep -q '^HTTP/[0-9.]* 200' <<< "$h" && [ "$(csp "$h")" = "$DWG_CSP" ] && pass "the DWG worker alone may evaluate, held to the folder" || fail "the DWG worker: $(head -1 <<< "$h"), policy $(csp "$h")"
[ "$(code -H 'Sec-Fetch-Dest: document' "$BASE$CV/workers/libredwg-parser-worker.js")" = 403 ] && pass "the DWG worker opened on its own is refused" || fail "the DWG worker opened on its own is not refused"
wasm="$(heads -H 'Accept-Encoding: gzip' "$BASE$CV/workers/libredwg-web.wasm")"
grep -qi '^content-type: application/wasm' <<< "$wasm" && grep -qi '^content-encoding: gzip' <<< "$wasm" \
	&& pass "the DWG wasm goes out gzipped ($(sed -n 's/^[Cc]ontent-[Ll]ength: //p' <<< "$wasm") bytes)" || fail "the DWG wasm is not served compressed as application/wasm"
# The folder names match in any case (the dev bind mount ignores case): no case variant is served outside the fence.
for page in "/assets/construction_core/vendor/CADVIEWER-1.7.6/index.html" "/assets/construction_core/vendor/CadViewer-1.7.6/index.html" "/assets/construction_core/vendor/OPENCADSTUDIO-0e4c4c3/index.html"; do
	got="$(code -H 'Sec-Fetch-Dest: document' "$BASE$page")"
	[ "$got" != 200 ] && pass "a case variant is fenced too ($got): $page" || fail "a case variant is served outside the fence: $page"
done
# The notices and the page's source (the GPL's offer) open on their own, as plain text under a policy that runs nothing.
for f in NOTICE.txt licenses/GPL-3.0.txt source/dev/cadviewer/src/main.js; do
	h="$(heads -H 'Sec-Fetch-Dest: document' "$BASE$CV/$f")"
	grep -q '^HTTP/[0-9.]* 200' <<< "$h" && grep -qi '^content-type: text/plain' <<< "$h" && [ "$(csp "$h")" = "$TEXT_CSP" ] \
		&& pass "$f opens on its own as plain text" || fail "$f on its own: $(head -1 <<< "$h"), $(sed -n 's/^[Cc]ontent-[Tt]ype: //p' <<< "$h"), $(csp "$h")"
done
for path in "$CV/..%2F..%2F..%2F..%2Fapi/method/ping" "$CV%2F..%2F..%2F..%2F..%2Fapi/method/ping.html" "$CV/workers/..%2F..%2F..%2F..%2F..%2Fapi/method/ping" "$CV/.%2e%2Fprivate/files/x.html" "$CV/source/..%2F..%2F..%2F..%2F..%2Fapi/method/ping"; do
	got="$(code "$BASE$path")"
	[ "$got" = 400 ] && pass "refused: $path" || fail "not refused ($got): $path"
done

for f in index.html LICENSE NOTICE.txt fonts/fonts.json fonts/OFL-Liberation.txt fonts/OFL-NotoSansMath.txt licenses/GPL-3.0.txt licenses/PACKAGES.txt source/dev/cadviewer/src/main.js source/dev/cadviewer/package-lock.json source/dev/build-cadviewer.sh source/dev/shell-images.sh workers/mtext-renderer-worker.js workers/libredwg-parser-worker.js workers/libredwg-web.wasm.gz; do
	[ -s "$CV_DIR/$f" ] && pass "the viewer's folder has $f" || fail "the viewer's folder lacks $f"
done
fonts="$(grep -o '"file": *"[^"]*"' "$CV_DIR/fonts/fonts.json" 2>/dev/null | sed 's/.*"\([^"]*\)"$/\1/')"
[ -n "$fonts" ] && [ -z "$(while read -r f; do [ -s "$CV_DIR/fonts/$f" ] || echo "$f"; done <<< "$fonts")" ] && ! grep -qi 'cad-data\|jsdelivr\|https\?:' "$CV_DIR/fonts/fonts.json" \
	&& pass "fonts.json names $(wc -l <<< "$fonts") fonts, all ours and in the folder" || fail "fonts.json is missing, empty, or names a font that is not ours or not there"
[ -s "$CV_DIR/index.html" ] && perl -0ne 'exit 1 if /<style\b/i || /<script\b(?![^>]*(?<![\w-])src\s*=)[^>]*>/i' "$CV_DIR/index.html" && pass "the viewer's page has no inline code" || fail "inline code in the viewer's page (or no page)"
grep -q 'cad-simple-viewer@' "$CV_DIR/licenses/PACKAGES.txt" 2>/dev/null && ! grep -Eq '@mlightcad/cad-viewer@|drive' "$CV_DIR/licenses/PACKAGES.txt" \
	&& pass "no cad-viewer and no drive plugin in the build" || fail "a package that calls Google or Microsoft is in the build (or no package list)"
grep -q 'libredwg-web/tree/v0.8.0' "$CV_DIR/NOTICE.txt" 2>/dev/null \
	&& [ "$(sha256sum < "$CV_DIR/licenses/GPL-3.0.txt" 2>/dev/null | cut -d' ' -f1)" = 8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903 ] \
	&& [ "$(sha256sum < "$CV_DIR/workers/libredwg-web.wasm" | cut -d' ' -f1)" = 18cdcf636310257b62449342cd7d6344f6231227e108872231004111fe39d0cb ] \
	&& pass "the DWG wasm is libredwg-web 0.8.0's, and the notice and GPL text name its source" || fail "the DWG wasm, its source link or the GPL text"

[ "$fails" -eq 0 ] && echo "OK: 0 failure(s)" || echo "FAILED: $fails failure(s)"
[ "$fails" -eq 0 ]
