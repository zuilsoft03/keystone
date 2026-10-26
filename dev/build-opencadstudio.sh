#!/usr/bin/env bash
# Builds the Open CAD Studio web bundle (P3-48, D-319) from a pinned upstream commit, as its own
# .github/workflows/pages.yml does, and vendors it under construction_core's public folder. Upstream publishes no
# web bundle with its releases, so it is built here, in a throwaway Rust container. The program stays separate
# (GPL-3.0): the workspace frames it, passes it a file's bytes and takes its saves back.
#
# The pin is main at 0e4c4c3 (2026-10-17, upstream CI green on Linux, macOS, Windows and wasm32): v2026.41 predates
# the hook that hands a save to the embedding page (85627eb, 2026-10-13). Move to the next release once it has it,
# and change CAD_APP in apps/construction_shell/frontend/src/viewer.js with the folder name.
#
#   bash dev/build-opencadstudio.sh
set -euo pipefail
REF="${1:-0e4c4c311df6de0d721bbf5fbf05c86dba19b368}"
RUST_IMAGE="rust:1-bookworm@sha256:e12566d5abc17a0da741628782cdb504b68b8961f5bfcf677936bf3e8b32de29"  # pinned (cf. D-112)
VER="${2:-0e4c4c3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/apps/construction_core/construction_core/public/vendor/opencadstudio-$VER"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

HOST_ROOT="$ROOT"; HOST_OUT="$OUT"
command -v cygpath >/dev/null 2>&1 && { HOST_ROOT="$(cygpath -m "$ROOT")"; HOST_OUT="$(cygpath -m "$OUT")"; }  # Git Bash
MSYS_NO_PATHCONV=1 docker run --rm -v "$HOST_ROOT/dev/build-opencadstudio-inner.sh:/build.sh:ro" -v "$HOST_OUT:/out" \
  -v cc-opencadstudio-cargo:/usr/local/cargo/registry "$RUST_IMAGE" \
  sh -c "mkdir -p /src && sh /build.sh '$REF' '/assets/construction_core/vendor/opencadstudio-$VER/'"

rm -rf "$DEST"
cp -r "$OUT/app" "$DEST"
cp "$OUT/LICENSE" "$DEST/LICENSE"
cp "$OUT/commit.txt" "$DEST/SOURCE_COMMIT"
# The welcome screen's feeds name YouTube videos and GitHub discussions; their thumbnails would load from the
# internet. Emptied, so the viewer reaches nothing outside the office (D-316).
echo '[]' > "$DEST/videos.json"
echo '[]' > "$DEST/discussions.json"
echo '[]' > "$DEST/supporters.json"  # upstream's CI writes it next to the app
# CSP (P3-48, audit M3): the page's inline style and scripts move to files in the folder, so the policy in
# deploy/nginx/frappe.conf.template holds no per-build hash. The service worker is dropped: the policy refuses it, and
# a cache of what the frame fetched is one more copy to wipe (cadstore.js).
(
  cd "$DEST"
  perl -0777 -pi -e '
    sub out { my ($n, $b) = @_; open(my $f, ">", $n) or die "$n: $!"; print $f $b; close $f; }
    s{<style>(.*?)</style>}{out("ocs-splash.css", $1); q{<link rel="stylesheet" href="ocs-splash.css" />}}se or die "no style\n";
    s{<script type="module">(.*?)</script>}{out("ocs-boot.js", $1); q{<script type="module" src="ocs-boot.js"></script>}}se or die "no module script\n";
    s{<script>(?:(?!</script>).)*?serviceWorker(?:(?!</script>).)*?</script>}{}s or die "no sw script\n";
    s{<script>((?:(?!</script>).)*?)</script>}{out("ocs-splash.js", $1); q{<script src="ocs-splash.js"></script>}}se or die "no splash script\n";
  ' index.html
  rm -f sw.js
  cat > MODIFICATIONS.txt <<NOTE
Open CAD Studio (GPL-3.0, see LICENSE), built from https://github.com/HakanSeven12/OpenCADStudio at
$(cat SOURCE_COMMIT) by dev/build-opencadstudio.sh of the Construction Workspace repository.
The program is unchanged. Its web page wrapper is changed: the inline style and scripts of index.html are moved into
ocs-splash.css, ocs-boot.js and ocs-splash.js, the service worker (sw.js and its registration) is removed, and
videos.json, discussions.json and supporters.json are emptied.
NOTE
  if grep -Eq '<script( type="module")?>|<style>|serviceWorker' index.html; then echo "inline script or style left in index.html" >&2; exit 1; fi
)
echo "Vendored Open CAD Studio $REF at $(cat "$DEST/SOURCE_COMMIT") into $DEST"
