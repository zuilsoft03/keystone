# Deploy profiles (P1-10, DR-1, D-083)

Each profile is its own image, built from pinned commits and digests. Never install into a running stack: a
change is a new image.

| Profile | What runs | Pins |
|---|---|---|
| `core` | Frappe + `construction_core` (no ERPNext, D-104), MariaDB, Redis | `profiles/core/apps-versions.json` |
| `core+office` | `core` + the ONLYOFFICE Document Server (internal network, JWT, no egress) | `profiles/core+office/apps-versions.json` |
| `full` | `core+office` + ERPNext (for the optional `ws_erpnext`, D-104) + the adapter build needs (ffmpeg, build-essential); adapters arrive pinned by commit in P3+ | `profiles/full/apps-versions.json` |

The MVP deploys `core+office` (D-099, D-102): office
files open in ONLYOFFICE behind `/office/` (P1-17). Deploying, backups, restore and upgrades: **`RUNBOOK.md`**.

## Build and verify

```bash
bash deploy/verify-pins.sh          # G-38: every SHA and digest pinned; ffmpeg only in full
bash deploy/build.sh core           # -> construction-workspace:core
```

`build.sh` runs `verify-pins.sh`, then builds the Frappe base (plus ERPNext for `full` only, D-104) with `dev/build-core-image.sh` (the
profile's commits and Python digest), then bakes our app in with `Containerfile.pinned`.

## Run

```bash
docker compose --env-file /etc/construction-workspace/stack.env -f deploy/compose.yml --profile office up -d
CW_ENV_FILE=/etc/construction-workspace/stack.env bash deploy/init-site.sh
CW_ENV_FILE=/etc/construction-workspace/stack.env bash deploy/check-staging.sh   # G-48
CW_ENV_FILE=/etc/construction-workspace/stack.env bash deploy/check-offsite.sh   # G-52: the NAS copy
CW_ENV_FILE=/etc/construction-workspace/stack.env bash deploy/check-golive.sh    # go-live settings (RUNBOOK §12)
```

`seed-check.sh` makes the check accounts the checks sign in with. `check-routes.sh` also runs `check-public.sh`: what
a guest gets from each public page, and each page's Permissions-Policy.

Only `proxy` (Caddy) publishes ports. Settings and secrets live in an env file outside the repository
(`RUNBOOK.md` §2). `bash deploy/staging.sh up|drill|check` runs the same stack on this machine at
`https://staging.localhost:8443`, with a certificate from Caddy's internal CA. `staging.sh up` also adds staging stand-ins
for what people do on the office server (an outgoing mail account that sends nowhere, the set-up wizard finished), so
`check-golive.sh` can pass there.

## The network

The `edge` network (proxy and frontend only) has a fixed subnet, `198.18.240.0/28` (`EDGE_SUBNET`), and nginx believes
`X-Forwarded-For` from it alone. Frappe believes any `X-Forwarded-For`, so the backend's gunicorn listens only on its
`default`-network address (alias `cc-backend`): the Document Server and clamd share a network with it but cannot reach
port 8000.

## Updating a pin

Change the commit or digest in every profile's `apps-versions.json` (and the dev defaults in
`dev/build-core-image.sh` for Frappe, and for ERPNext in `full`), run `verify-pins.sh`, rebuild, run the full suite on `core`.
Node is pinned to its major version (`24`) by the upstream recipe, which installs it through nvm.

## Realtime behind the proxy

The realtime server accepts a browser only when `Host` matches `Origin`. It then authenticates the user by calling
`<Origin>/api/method/...`. `nginx/frappe.conf.template` first refuses any `/socket.io` request whose Origin is not
exactly the requested host and port, then sets Origin to `http://<site>:8080` and Host to the site name. The
`frontend` service carries the site name as a network alias, so that call stays inside the stack: it needs neither
public DNS nor the public certificate. The dev stack instead gives `backend` the alias `dev.localhost` and sets
`webserver_port` (dev mode).
