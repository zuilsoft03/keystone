#!/usr/bin/env bash
# Builds the Files viewer's DWG/DXF page (P3-49, D-328, D-329): mlightcad's cad-simple-viewer 1.7.6 (MIT) with the
# LibreDWG converter and worker (GPL-3.0) and our own OFL fonts, into construction_core's vendor folder, where nginx
# serves it under its own policy (deploy/nginx/frappe.conf.template). Nothing it loads at run time comes from outside
# that folder.
#
# - The page (dev/cadviewer) is built in the pinned Node image of dev/shell-images.sh: `npm ci` installs exactly the
#   packages in dev/cadviewer/package-lock.json, each checked against its integrity hash, then `vite build`.
# - The MTEXT worker, the DWG worker and its wasm are copied unchanged from their packages' dist folders; the wasm is
#   checked against its pin (it is libredwg-web 0.8.0's, whatever version npm resolved beside it).
# - The page bundles @mlightcad/libredwg-converter (GPL-3.0), so the page as a whole is offered under the GPL-3.0:
#   the GPL text (pinned) goes in licenses/, and the page's own source (dev/cadviewer, with its lockfile) in source/.
# - The fonts are Liberation 2.1.5 and Noto Sans Math 3.000 (both SIL OFL 1.1), downloaded from their releases and
#   checked against the SHA-256 below. Never mlightcad/cad-data: it has no licence and holds Microsoft and Autodesk
#   fonts.
# - Text files and the wasm get a .gz beside them for nginx's gzip_static (the wasm is 10 MB, about 2.5 MB gzipped).
# - Never @mlightcad/cad-viewer: its Drive and OneDrive plugins call Google and Microsoft. The build fails if the
#   lockfile names it or any drive plugin, at any depth.
#
#   bash dev/build-cadviewer.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep container paths as written
cd "$(dirname "$0")/.."
. dev/shell-images.sh
VER="1.7.6"
DEST="apps/construction_core/construction_core/public/vendor/cadviewer-$VER"
LIB_URL="https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz"
LIB_SHA="7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0"
MATH_URL="https://github.com/notofonts/math/releases/download/NotoSansMath-v3.000/NotoSansMath-v3.000.zip"
MATH_SHA="ac351837b41f8a897f020b97fb0f075ad574c1e9669fb5839ada1f92fd748356"
GPL_URL="https://raw.githubusercontent.com/mlightcad/libredwg-web/v0.8.0/COPYING"
GPL_SHA="8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903"
WASM_SHA="18cdcf636310257b62449342cd7d6344f6231227e108872231004111fe39d0cb"  # @mlightcad/libredwg-web 0.8.0's wasm
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
HOST_SRC="$PWD/dev/cadviewer"; HOST_OUT="$OUT"
command -v cygpath >/dev/null 2>&1 && { HOST_SRC="$(cygpath -m "$HOST_SRC")"; HOST_OUT="$(cygpath -m "$OUT")"; }

# The page and its workers. The sources are copied into the container, so node_modules never lands on the host.
docker run --rm -v "$HOST_SRC:/app:ro" -v "$HOST_OUT:/out" -v cw-npm-cache:/root/.npm "$NODE_IMAGE" sh -euc '
	mkdir -p /work && cp -r /app/. /work/ && rm -rf /work/node_modules /work/dist && cd /work
	node -e "
		const names = Object.keys(require(\"./package-lock.json\").packages)
		const bad = names.filter((k) => /(^|\/)@mlightcad\/cad-viewer$|drive/i.test(k))
		if (bad.length) { console.error(\"build-cadviewer.sh: a package that calls Google or Microsoft is locked: \" + bad.join(\", \")); process.exit(1) }"
	npm ci --ignore-scripts --no-audit --no-fund --loglevel=error
	npx vite build --logLevel warn
	mkdir -p dist/workers dist/licenses
	cp node_modules/@mlightcad/cad-simple-viewer/dist/mtext-renderer-worker.js dist/workers/
	cp node_modules/@mlightcad/libredwg-converter/dist/libredwg-parser-worker.js node_modules/@mlightcad/libredwg-converter/dist/libredwg-web.wasm dist/workers/
	for p in node_modules/@mlightcad/* node_modules/three node_modules/lodash-es node_modules/@lukeed/* node_modules/@velipso/* node_modules/idb node_modules/opentype.js node_modules/iconv-lite node_modules/safer-buffer node_modules/tslib node_modules/uid node_modules/loglevel; do
		for f in "$p"/LICENSE* "$p"/NOTICE* "$p"/license*; do [ -f "$f" ] && cp "$f" "dist/licenses/$(echo "${p#node_modules/}" | tr / _)-$(basename "$f")"; done
	done
	npm ls --all --omit=dev > dist/licenses/PACKAGES.txt
	cp -r dist /out/app'

echo "$WASM_SHA  $OUT/app/workers/libredwg-web.wasm" | sha256sum -c --quiet
# Every script of the page is a file with a src, and it has no style element: the folder's policy allows no inline code.
perl -0ne 'exit 1 if /<style\b/i || /<script\b(?![^>]*(?<![\w-])src\s*=)[^>]*>/i' "$OUT/app/index.html" || { echo "inline script or style in index.html" >&2; exit 1; }

# The fonts and the GPL text, checked against their pins.
mkdir -p "$OUT/fonts" "$OUT/app/fonts"
curl -fsSL -o "$HOST_OUT/fonts/lib.tgz" "$LIB_URL"
curl -fsSL -o "$HOST_OUT/fonts/math.zip" "$MATH_URL"
curl -fsSL -o "$HOST_OUT/app/licenses/GPL-3.0.txt" "$GPL_URL"
echo "$LIB_SHA  $OUT/fonts/lib.tgz" | sha256sum -c --quiet
echo "$MATH_SHA  $OUT/fonts/math.zip" | sha256sum -c --quiet
echo "$GPL_SHA  $OUT/app/licenses/GPL-3.0.txt" | sha256sum -c --quiet
tar xzf "$OUT/fonts/lib.tgz" -C "$OUT/fonts"
unzip -q "$OUT/fonts/math.zip" -d "$OUT/fonts/math"
for f in Sans Serif Mono; do cp "$OUT/fonts/liberation-fonts-ttf-2.1.5/Liberation$f-Regular.ttf" "$OUT/app/fonts/"; done
cp "$OUT/fonts/liberation-fonts-ttf-2.1.5/LICENSE" "$OUT/app/fonts/OFL-Liberation.txt"
cp "$OUT/fonts/math/NotoSansMath/unhinted/ttf/NotoSansMath-Regular.ttf" "$OUT/app/fonts/"
cp "$OUT/fonts/math/OFL.txt" "$OUT/app/fonts/OFL-NotoSansMath.txt"
cp dev/cadviewer/fonts/fonts.json "$OUT/app/fonts/"

# The page's own source, for the GPL: what this script builds from, laid out as in our repository, with the exact
# versions in its lockfile. `bash dev/build-cadviewer.sh` run inside source/ rebuilds the page (with Docker and the
# network for npm and the fonts).
mkdir -p "$OUT/app/source/dev/cadviewer"
(cd dev/cadviewer && cp -r package.json package-lock.json vite.config.js index.html src fonts "$OUT/app/source/dev/cadviewer/")
cp dev/build-cadviewer.sh dev/shell-images.sh "$OUT/app/source/dev/"

# The notices: the page is GPL-3.0 as a whole; its parts keep their own licences.
cp "$OUT/app/licenses/@mlightcad_cad-simple-viewer-LICENSE" "$OUT/app/LICENSE"
cat > "$OUT/app/NOTICE.txt" <<NOTE
Drawing viewer of the Construction Workspace, built by dev/build-cadviewer.sh from dev/cadviewer.

This page bundles @mlightcad/libredwg-converter 3.15.11 (its package.json says GPL-3.0), so the page as a whole
(assets/, workers/) is offered under the GNU General Public License version 3: licenses/GPL-3.0.txt. Its source is
source/ (our page in source/dev/cadviewer and its build script source/dev/build-cadviewer.sh; package-lock.json names
every package version) with the packages below.

- @mlightcad/cad-simple-viewer $VER and its @mlightcad dependencies (MIT; LICENSE and licenses/; @mlightcad/data-model
  ships no licence file and is MIT by its package.json, under mlightcad's MIT text in LICENSE):
  https://github.com/mlightcad/cad-viewer/tree/v$VER and https://github.com/mlightcad/realdwg-web/tree/v1.15.11
- @mlightcad/emf-converter (Apache-2.0; licenses/, with its NOTICE).
- @mlightcad/libredwg-converter 3.15.11 (GPL-3.0; the MIT file in its tarball, licenses/@mlightcad_libredwg-converter-
  LICENSE, is not taken as its licence): bundled into assets/, and its worker workers/libredwg-parser-worker.js.
  Source: https://github.com/mlightcad/realdwg-web/tree/v1.15.11
- workers/libredwg-web.wasm and the LibreDWG code in the worker: @mlightcad/libredwg-web 0.8.0, LibreDWG compiled to
  WebAssembly, GPL-3.0 (licenses/GPL-3.0.txt). Source: https://github.com/mlightcad/libredwg-web/tree/v0.8.0
  (LibreDWG with its JavaScript bindings). Copied unchanged. The libredwg-web 0.8.1 that npm installs beside the
  converter (licenses/PACKAGES.txt) is not used: none of its code is in the page or the workers.
- three, lodash-es, opentype.js, iconv-lite, safer-buffer, uid, @lukeed/csprng, loglevel (MIT); idb (ISC); tslib,
  @velipso/polybool (0BSD): licenses/.
- fonts/: Liberation Sans, Serif and Mono 2.1.5 and Noto Sans Math 3.000, SIL Open Font License 1.1
  (fonts/OFL-Liberation.txt, fonts/OFL-NotoSansMath.txt). fonts.json is ours: it names the SHX and system fonts a
  drawing may ask for, so they are drawn with these.
NOTE

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -r "$OUT/app" "$DEST"
(
	cd "$DEST"
	find . -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.json' -o -name '*.wasm' -o -name '*.ttf' \) ! -path './source/*' -exec gzip -9 -k -n -f {} \;
	find . -type f ! -name '*.gz' ! -name SHA256SUMS | sort | xargs sha256sum > SHA256SUMS
)
echo "Built the drawing viewer $VER into $DEST ($(du -sh "$DEST" | cut -f1))"
