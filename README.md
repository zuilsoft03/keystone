# Keystone

Keystone is a project workspace for construction firms. Designers, project staff and clients work on the same
project: discussion, files and versions, drawings and PDF previews, takeoffs, approvals with signed receipts,
RFIs, submittals, variation orders, BOQ, progress billing, site daily reports and punch lists.

Each firm runs its own site with its own brand. Keystone runs on-premise or on any server that runs Docker.

## Stack

- **Backend:** [Frappe Framework](https://frappe.io/framework) v16. ERPNext is not required.
- **Frontend:** a Vue 3 + [frappe-ui](https://github.com/frappe/frappe-ui) single-page app for staff and clients.
- **Optional services:** ONLYOFFICE Document Server for office files, a preview renderer for drawings and PDFs,
  and ClamAV for upload scanning.

## Layout

| Path | Contents |
|---|---|
| `apps/construction_core/` | The Frappe app: doctypes, permissions, storage, approvals, discussion, onboarding. |
| `apps/construction_shell/` | The web app (SPA) that staff and clients use, and its Frappe pages. |
| `deploy/` | Production images, compose file, backups, restore and go-live checks. Start at `deploy/README.md`. |
| `dev/` | The local development stack. |
| `docs/` | The construction project lifecycle and the design-phase lifecycle. |

## Run it locally

You need Docker and Bash (on Windows, Git Bash).

```bash
bash dev/build-core-image.sh
```

```bash
bash dev/up.sh
```

The first command builds the Frappe image once. The second starts the stack and makes the site `dev.localhost` with both apps installed. It generates the passwords
once into `dev/.env`, which git ignores. For demo projects and users, run `bash dev/seed-demo.sh`.

## Deploy

`deploy/RUNBOOK.md` tells you how to build, start, back up, restore, upgrade and go live. Read
`deploy/README.md` first for the deploy profiles.

## Licence

Keystone is free software under the [GNU Affero General Public License v3.0](LICENSE). If you run a changed
version for other people over a network, you must give them its source code.

Third-party parts keep their own licences: see `apps/construction_core/construction_core/public/vendor/VENDOR.md`
and `deploy/renderer/THIRD-PARTY.md`.
