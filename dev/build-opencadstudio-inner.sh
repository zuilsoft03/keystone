#!/bin/sh
# Runs inside the pinned Rust image for dev/build-opencadstudio.sh: checks out the pinned commit (or tag), builds the web
# bundle with trunk at the given public URL, and copies it, the licence and the source commit to /out.
set -eu
REF="$1"
PUBLIC_URL="$2"
apt-get update -qq && apt-get install -y -qq git >/dev/null
rustup target add wasm32-unknown-unknown
cd /src
git clone --quiet https://github.com/HakanSeven12/OpenCADStudio.git ocs
cd ocs
git checkout --quiet "$REF"
git rev-parse HEAD > /out/commit.txt
cp LICENSE /out/LICENSE
WB=$(sed -n '/name = "wasm-bindgen"/{n;s/version = "\(.*\)"/\1/p;q;}' Cargo.lock)
# Built from crates.io at pinned versions, with no installer script: trunk 0.21.14 (as upstream's CI used it) and
# wasm-bindgen-cli at the version the lock file names. trunk fetches wasm-opt at the version it pins.
cargo install --locked --quiet trunk@0.21.14 "wasm-bindgen-cli@$WB"
trunk build --locked --release --public-url "$PUBLIC_URL" --dist dist/app --html-output index.html web-app.html
rm -rf /out/app && cp -r dist/app /out/app
