# Vendored browser libraries (P1-15, P1-18)

These are prebuilt browser bundles copied unchanged from the npm registry. Each tarball was checked against the
registry's published `dist.integrity` before copying. The runtime image has no Node toolchain, so libraries are
vendored rather than built. To update: download the new tarball, verify its integrity, replace the folder, and
update this table.

| Library | Version | License | Source tarball | Files kept |
|---|---|---|---|---|
| @excalidraw/excalidraw | 0.17.6 | MIT (package.json; bundled notices in `excalidraw.production.min.js.LICENSE.txt`) | https://registry.npmjs.org/@excalidraw/excalidraw/-/excalidraw-0.17.6.tgz | `dist/excalidraw.production.min.js`, `dist/excalidraw-assets/` |
| react | 18.3.1 | MIT (`LICENSE`) | https://registry.npmjs.org/react/-/react-18.3.1.tgz | `umd/react.production.min.js` |
| react-dom | 18.3.1 | MIT | https://registry.npmjs.org/react-dom/-/react-dom-18.3.1.tgz | `umd/react-dom.production.min.js` |
| pdfjs-dist (P1-18) | 4.10.38 | Apache-2.0 (`LICENSE`) | https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-4.10.38.tgz | `build/pdf.min.mjs` and `build/pdf.worker.min.mjs`, kept byte-identical but renamed to `.js` (nginx serves `.mjs` without a JavaScript type, which browsers refuse for modules); `standard_fonts/`, `cmaps/` |

SHA-256 of the files kept (to re-verify without downloading):

```
27b133f845543f091aa518924b5b2fdd7eb52a9e490de100b9bc3bfd2ae2f314 *excalidraw-0.17.6/excalidraw.production.min.js
d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd *react-18.3.1/react.production.min.js
35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d *react-18.3.1/react-dom.production.min.js
27fc2a057a00f92a4334ad06e17dbd7259912954e9fb7f76400bcca5fd190a9c *pdfjs-4.10.38/pdf.min.js
1baa1844c89c80a5b2797c916e75ab29254be46d8e9cb53cb6364d7aad84be36 *pdfjs-4.10.38/pdf.worker.min.js
```

PDF.js is 4.10.38, after the fix for CVE-2024-4367 (4.2.67); pages render with `isEvalSupported: false` as well.

## Open CAD Studio (P3-48, D-318, D-319)

Open CAD Studio is not an npm package and its releases carry no web bundle. `dev/build-opencadstudio.sh` builds
it from source in a throwaway `rust:1-bookworm` container pinned by digest, with trunk 0.21.14 and wasm-bindgen-cli
installed by `cargo install --locked`, with the trunk steps of upstream's
`.github/workflows/pages.yml`, into `opencadstudio-0e4c4c3/` with its `LICENSE` and `SOURCE_COMMIT`. The folder
is git-ignored (117 MB; Q-104 is how it reaches production images). The build empties `videos.json`,
`discussions.json` and `supporters.json`; moves `index.html`'s inline style and scripts into `ocs-splash.css`,
`ocs-boot.js` and `ocs-splash.js`, so the folder's Content-Security-Policy (deploy/nginx/frappe.conf.template, D-325)
needs no per-build hash; and drops its service worker (`sw.js` and its registration). The program itself is not
changed; `MODIFICATIONS.txt` in the folder says so for the GPL.

| Program | Version | License | Source | Kept |
|---|---|---|---|---|
| opencadstudio | upstream main at 0e4c4c311df6de0d721bbf5fbf05c86dba19b368 (2026-10-17; v2026.41 lacks the save hook) | GPL-3.0 (`LICENSE`), a separate program in its own frame | https://github.com/HakanSeven12/OpenCADStudio | the whole `dist/app` of `trunk build --release` |

SHA-256 of the main files of this build (a rebuild of the same commit can differ in its file names):

```
0a41893fed978979d310957998e83a0dce53ba55bb422b95cb80ee73d70911c1 *opencadstudio-0e4c4c3/OpenCADStudio-15b2bf26d3cf7f9d_bg.wasm
94c49a77dfe763b479f51fd61693ac241302615b185c7ac8fae4f79399c0c9af *opencadstudio-0e4c4c3/OpenCADStudio-15b2bf26d3cf7f9d.js
83bf13d608797a6d30622c05e1eb6ec4ffefa2cad831a6d8279a6036b013b220 *opencadstudio-0e4c4c3/worker_pkg/ocs_web_worker_bg.wasm
```

## The drawing viewer (P3-49, D-328, D-329, D-330)

`dev/build-cadviewer.sh` builds the Files viewer's DWG/DXF page from `dev/cadviewer/` (our page: `index.html`,
`src/main.js`, `fonts/fonts.json`) in the pinned Node image: `npm ci` from the committed lockfile, `vite build`, then
the MTEXT worker, the DWG worker and its wasm copied unchanged from their packages (the wasm checked against its pin),
and the fonts and the GPL text downloaded and checked against the SHA-256 in the script. It writes `cadviewer-1.7.6/`
with `LICENSE`, `NOTICE.txt`, `licenses/` (every package's licence file, `GPL-3.0.txt` and `PACKAGES.txt`), `source/`
(the page's own source and the build script) and `SHA256SUMS`, and a `.gz` beside each text file and the wasm for
nginx's `gzip_static`. The folder is git-ignored (about 23 MB with the `.gz` files; Q-104). The build fails if the
lockfile names `@mlightcad/cad-viewer` or a drive plugin at any depth, or if the page has inline code. On the wire a
cold open of a DWG is about 4.6 MB (the page 1.1 MB, the MTEXT worker 0.37 MB, the DWG worker and wasm 2.55 MB,
Liberation Sans and Noto Sans Math 0.55 MB), all gzipped; Open CAD Studio is 117 MB.

**Licence of the page as a whole: GPL-3.0.** The page bundles `@mlightcad/libredwg-converter` (its package.json says
GPL-3.0; the MIT file in its tarball is not taken as its licence), and its worker carries LibreDWG. So the page and
its workers are offered under the GPL-3.0 (`licenses/GPL-3.0.txt`), with their source: `source/` (our page, its
lockfile and the build script) and the upstream sources below. The other parts keep their own licences, all
GPL-compatible. `NOTICE.txt`, the GPL text, the licence files and `source/` open on their own as plain text (the rest
of the folder is refused outside the viewer's frame); the viewer's footer links `NOTICE.txt` and both sources.

| Library | Version | License | Source | Kept |
|---|---|---|---|---|
| @mlightcad/cad-simple-viewer | 1.7.6 | MIT (`LICENSE`) | https://registry.npmjs.org/@mlightcad/cad-simple-viewer/-/cad-simple-viewer-1.7.6.tgz (https://github.com/mlightcad/cad-viewer/tree/v1.7.6) | bundled into `assets/index-*.js`; `workers/mtext-renderer-worker.js` unchanged |
| @mlightcad/three-renderer, data-model, mtext-renderer, mtext-parser and their @mlightcad dependencies | 1.7.6, 1.15.11, 0.13.4, 1.5.5 (exact pins in `dev/cadviewer/package-lock.json`) | MIT (`licenses/`) | https://github.com/mlightcad/realdwg-web/tree/v1.15.11, https://github.com/mlightcad/mtext-renderer | bundled |
| @mlightcad/emf-converter | 1.15.11 | Apache-2.0 (`licenses/@mlightcad_emf-converter-LICENSE`, `-NOTICE.md`) | npm registry | bundled |
| three, lodash-es, opentype.js, iconv-lite, safer-buffer, uid, @lukeed/csprng, loglevel, idb, tslib, @velipso/polybool | as locked | MIT; ISC (idb); 0BSD (tslib, @velipso/polybool) (`licenses/`) | npm registry | bundled |
| @mlightcad/libredwg-converter | 3.15.11 | GPL-3.0 (`licenses/GPL-3.0.txt`) | https://github.com/mlightcad/realdwg-web/tree/v1.15.11 | bundled into `assets/index-*.js`; `workers/libredwg-parser-worker.js` unchanged |
| @mlightcad/libredwg-web (LibreDWG compiled to WebAssembly) | 0.8.0: the wasm the converter ships (SHA-256 below), not the 0.8.1 npm resolves beside it | GPL-3.0 (`licenses/GPL-3.0.txt`, its `COPYING`) | https://github.com/mlightcad/libredwg-web/tree/v0.8.0 | `workers/libredwg-web.wasm` unchanged, run in its own worker |
| Liberation Sans, Serif, Mono | 2.1.5 | SIL OFL 1.1 (`fonts/OFL-Liberation.txt`) | https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz | the three Regular TTFs |
| Noto Sans Math | 3.000 | SIL OFL 1.1 (`fonts/OFL-NotoSansMath.txt`) | https://github.com/notofonts/math/releases/download/NotoSansMath-v3.000/NotoSansMath-v3.000.zip | `NotoSansMath-Regular.ttf` (unhinted) |

`fonts/fonts.json` is ours, not mlightcad/cad-data's (which has no licence and holds Microsoft and Autodesk fonts): it
names the SHX and system fonts a drawing may ask for (txt, simplex, romans, isocp, Arial, Times New Roman, Courier
New and others) as aliases of these four, so text is drawn in them; amgdt and gdt map to Noto Sans Math, whose ∅ is what
the viewer draws for `%%c`. There is no CJK font: Chinese, Japanese and Korean text shows as `?`.

SHA-256 of the files kept (the page bundle's name changes with its content):

```
267d99826f8619d8bddb3934fc2863bd83ffbd9b0f8f851847e7c60780dfd577 *cadviewer-1.7.6/workers/libredwg-parser-worker.js
8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903 *cadviewer-1.7.6/licenses/GPL-3.0.txt
18cdcf636310257b62449342cd7d6344f6231227e108872231004111fe39d0cb *cadviewer-1.7.6/workers/libredwg-web.wasm
2fa8ae023658947b39ce4d5ff8f628f7d917ea0fd4b563a61b9bab8dc2f40d18 *cadviewer-1.7.6/workers/mtext-renderer-worker.js
76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8 *cadviewer-1.7.6/fonts/LiberationSans-Regular.ttf
058ea80864aef09a23f45cbec2bb5400bc3dfbdea01c3f10538a21fcb497fb74 *cadviewer-1.7.6/fonts/LiberationSerif-Regular.ttf
f2b83c763e8afd21709333370bed4774337fae82267937e2b5aea7e2fbd922c1 *cadviewer-1.7.6/fonts/LiberationMono-Regular.ttf
b127e84699212b6b2ef50aff58e0ebebeec04ffe6db1b9eb9e209c8c3d97b4aa *cadviewer-1.7.6/fonts/NotoSansMath-Regular.ttf
```
