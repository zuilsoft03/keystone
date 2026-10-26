# The renderer's third-party parts (P3-75)

The renderer image adds two Python packages to the stack's own Python base, nothing else (design §15.1, §15.7:
permissive licences only, no PyMuPDF, ezdxf, LibreDWG, ODA or olefile). Each is pinned to an exact version and
installed from its wheel with `--require-hashes --no-deps --only-binary=:all:` (`requirements.txt`). The OLE2 reader
for Revit files is our own standard-library code (`previews/readers/ole.py`).

| Part | Version | Pin (sha256) | Licence | Where it came from |
|---|---|---|---|---|
| Python base image | `python:3.14.8-slim-trixie` | `a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170` (image digest) | PSF-2.0 (Python); Debian trixie packages under their own licences | The same pin as the app image (`deploy/profiles/*/apps-versions.json`, `base.python`) |
| Pillow | 12.3.0 | `251bf95b67017e27b13d82f5b326234ca62d70f9cf4c2b9032de2358a3b12c7b` (`pillow-12.3.0-cp314-cp314-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`) | MIT-CMU | PyPI, uploaded 2026-07-01; the same version Frappe v16 pins |
| pypdfium2 | 5.14.0 (PDFium 156.0.8076.0, pdfium-binaries) | `11f281613fa22313d9c7ab89947665e84eccf8ebe40e1198a84a88352305648d` (`pypdfium2-5.14.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`) | Apache-2.0 or BSD-3-Clause (bindings); PDFium BSD-3-Clause | PyPI, uploaded 2026-10-04; the version the ERPNext `full` profile installs |

Neither package has a runtime dependency (PyPI `requires_dist`: Pillow's are extras only, pypdfium2's none).

## Libraries inside the wheels

As shipped in the wheels (read from the built image: `pillow.libs/` and pypdfium2's `BUILD_LICENSES/`).

- **Pillow 12.3.0**: libjpeg-turbo 3 (IJG, BSD-3-Clause, zlib), libpng 1.6 (libpng), zlib 1.3.1 (zlib), libwebp 1.6.0
  with sharpyuv, demux and mux (BSD-3-Clause), libtiff 4.7.1 (libtiff), lcms2 2.19 (MIT), FreeType 2.14.3 (FTL, the
  BSD-style choice of its dual licence), HarfBuzz (MIT), OpenJPEG 2.5.4 (BSD-2-Clause), libavif 1.4.2 (BSD-2-Clause),
  liblzma 5.8.3 (0BSD), zstd 1.5.7 (BSD-3-Clause), brotli 1.2.0 (MIT), libxcb and libXau (MIT/X11).
- **pypdfium2 5.14.0**: PDFium (BSD-3-Clause), pdfium-binaries (MIT), abseil (Apache-2.0), agg 2.3 (BSD-style),
  fast_float (Apache-2.0 or MIT), FreeType (FTL), ICU (Unicode-3.0), lcms (MIT), libjpeg-turbo (IJG, BSD-3-Clause),
  OpenJPEG (BSD-2-Clause), libpng (libpng), llvm-libc (Apache-2.0 with LLVM exception), simdutf (Apache-2.0 or MIT),
  zlib (zlib); pypdfium2's own docs are CC-BY-4.0.

No GPL or AGPL code is linked into the renderer's process. The Debian base carries the usual system packages (bash,
coreutils and so on, some GPL), exactly as the app image already does; the renderer never links them.

## Updating

Change the version and hash in `requirements.txt` and this table together, from the package's PyPI JSON
(`https://pypi.org/pypi/<name>/<version>/json`, `urls[].digests.sha256` of the manylinux x86_64 wheel for CPython 3.14).
Take new pdfium-binaries releases (PDFium memory-safety fixes recur: research-previews.md §3.3). A change of a
reader's output also bumps `RENDERER_VERSION` (previews/__init__.py), so previews are made again on the next view.
