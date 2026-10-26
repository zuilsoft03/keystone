### Construction Shell

The staff workspace (`/workspace`) and, from P2-06, the client portal on the same shell: a standalone Vue 3 +
frappe-ui single-page app. It depends on `construction_core` and never the reverse; every check
stays on the server, and the app only presents.

- `construction_shell/www/ws_workspace.py` gates the page: a Guest goes to the login page, a Website User is refused,
  and any path the app does not know gets our own 404 (D-054, DR-3).
- `construction_shell/sections.json` names the sections. The server's path check and the app's router read the same
  file.
- `frontend/` is the Vite project. Its `package-lock.json` pins every package with an integrity hash. The delivery
  image builds it in its own stage (`deploy/Containerfile.pinned`), so a server never needs npm. In development,
  `bash dev/build-shell.sh` builds it in the same pinned Node image, into `construction_shell/public/shell/`
  (not committed).

