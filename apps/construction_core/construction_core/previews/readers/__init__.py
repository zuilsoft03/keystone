"""The readers of hostile bytes (P3-75, design §15.1, §15.2). They run only inside the renderer container, in a child
process that set its limits before it read anything (deploy/renderer/child.py); the backend imports them only in tests.

Standard library and Pillow only (pypdfium2 for PDF, imported where it is used), and never frappe: the renderer has
no site, no database and no network. Each reader gets a seekable file of the job's bytes and the preview's long edge,
and returns a ``Result`` or raises ``Refused`` with a fixed reason (``common.REASONS``).
"""
