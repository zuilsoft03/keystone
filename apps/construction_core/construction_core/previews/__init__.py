"""Previews and thumbnails (P3-75; R-32, design §15, D-416, D-417, D-421).

- **One pipeline.** A source (a chat attachment, a project file, a board) asks for a preview; a job on the ``thumbs``
  queue picks the reader by magic bytes, has the bytes drawn in the isolated renderer (or the Document Server, for
  Office), re-encoded to a WebP of at most 400 px with no metadata, and stored by content hash (``store``, ``jobs``).
- **Preview Image rows** hold the state per source and key: pending, ready, failed, skipped, with the reason. Rows with
  the same key share one stored file under ``<site>/private/thumbs/``: never a File, not backed up, made again on
  demand. A chat card reads the state from its own Discuss Attachment row, which the job keeps up to date, so a card
  costs no query of its own.
- **One endpoint** (``api.image``) serves a preview to a viewer the source's own rule lets in. The kinds of source are a
  registry (``sources``): a new kind is one registration plus its permission test.
- **Failures.** A fixed failure (locked, too large, blank, unreadable, killed by a limit) is kept for that key and
  renderer version and never retried; a passing one (the renderer, clamd or the Document Server down) is retried with
  backoff, a few times. A failed preview never fails an upload, a send or a save.
"""

SPEC = "p400"  # the preview's spec: 400 px on its long edge (discuss.media.PREVIEW_SPEC)
PX = 400
RENDERER_VERSION = "r2"  # a new version makes previews again on the next view (r2: Office, sha256 keys)
DOCTYPE = "Preview Image"
QUEUE = "thumbs"
