# MVP deploy runbook (P1-19)

The MVP runs the `core+office` profile (D-099, D-102, D-104): Frappe + `construction_core` (no ERPNext), the ONLYOFFICE
Document Server, MariaDB, Redis, a nightly backup, and Caddy in front for HTTPS. Everything is pinned
(`deploy/verify-pins.sh`); the app image is built from the pins (`deploy/build.sh`).

## 1. What the owner provides (Q-25)

| Item | Why |
|---|---|
| A Linux server: 4 vCPU, 16 GB RAM, 100 GB SSD (minimum 8 GB RAM without office editing) | The Document Server alone takes 2–4 GB; MariaDB, workers and the site take the rest. |
| A domain name, for example `projects.company.com`, with an A record pointing at the server | Caddy gets a Let's Encrypt certificate for it; ports 80 and 443 must be open to the internet. |
| An off-site place for backups (another server, S3-compatible storage, or a NAS) | Backups on the same server do not survive losing the server. |
| An outgoing mail account (Q-23) | Client invitations, password resets and notifications. |

## 2. Settings file

Create `/etc/construction-workspace/stack.env` (mode 600, owned by root; never in the repository):

```
COMPOSE_PROJECT_NAME=construction-workspace
APP_IMAGE=construction-workspace:core-office
RENDERER_IMAGE=construction-workspace:renderer   # P3-75: the preview renderer, built by deploy/build.sh
SITE_NAME=projects.company.com
TLS_ISSUER=it@example.com            # the ACME (Let's Encrypt) account email
HTTP_PORT=80
HTTPS_PORT=443
BACKUP_DIR=/var/backups/construction-workspace
OFFSITE_DIR=/mnt/nas/construction-workspace  # the NAS share, mounted on the host (§10.5)
DB_ROOT_PASSWORD=<generate: openssl rand -hex 32>
ADMIN_PASSWORD=<generate>
ONLYOFFICE_JWT_SECRET=<generate>
CHECK_USER=deploy-check@example.com  # a staff account used only by the readiness check
CHECK_PASSWORD=<generate>
OFFICE_FILE=<filled in after step 4>
CA_FILE=                             # empty: the certificate is publicly trusted
```

The `configurator` service sets `disable_render_safe_exec` to the integer `0` on every `up`, so templates render with
restricted globals (P3-76). Never set it to `None`, `1` or `"0"` and never hand-edit it; `check-staging.sh` checks it.

## 3. Build and start

Create the backup folder first, private to root: `install -d -m 700 /var/backups/construction-workspace`.

```bash
bash deploy/verify-pins.sh
bash deploy/build.sh core+office                     # also builds the renderer; or build elsewhere and `docker save | docker load` both
docker compose --env-file /etc/construction-workspace/stack.env -f deploy/compose.yml --profile office up -d
CW_ENV_FILE=/etc/construction-workspace/stack.env bash deploy/init-site.sh
```

When the images were built elsewhere and loaded, check that the renderer is the one built from these sources (P3-75):
`docker image inspect -f '{{index .Config.Labels "construction.renderer-inputs"}}' construction-workspace:renderer`
must print the inputs digest `deploy/build.sh` printed for this checkout.

`init-site.sh` creates the site (Frappe only, D-104), completes Frappe's setup (country, time zone, PHP), sets `host_name`, the scheduler
and the office editor's settings. It is safe to run again (it migrates instead).

The image carries both apps: `construction_core` and the workspace app `construction_shell` (`/workspace`, P2-02). The
workspace's web app is built inside the image build, from its lockfile, in a pinned Node image (D-111): the server needs
no npm or Node tools, only Docker. `init-site.sh` installs the shell on a site made before P2-02, and after every migrate
it clears the route caches (DR-2, D-114).

## 4. Check readiness (G-48, G-52)

Create the check accounts and the office file once: `CW_ENV_FILE=/etc/construction-workspace/stack.env bash
deploy/seed-check.sh` (P3-10). It adds the missing `CHECK_*` settings to the env file, with generated passwords, and
writes `OFFICE_FILE`. Then:

```bash
CW_ENV_FILE=/etc/construction-workspace/stack.env bash deploy/check-staging.sh
CW_ENV_FILE=/etc/construction-workspace/stack.env bash deploy/check-offsite.sh   # the NAS copy (§5)
```

Every line must be PASS: HTTP redirects to HTTPS with HSTS; the app port is closed; login gives a Secure cookie;
setup is complete; module scripts are served as JavaScript; realtime authenticates; office editing is configured;
every service is healthy; a recent, complete, checksummed backup exists; a restore drill passed.

**The workspace and portal routes (P2-07).** With the check client `seed-check.sh` made (a client contact of the
check project, its password in the env file as `CHECK_CLIENT_PASSWORD`), run:

```bash
CW_ENV_FILE=/etc/construction-workspace/stack.env bash deploy/check-routes.sh
```

It re-checks the routes over HTTPS: Guests go to login, an unknown `/workspace` or
`/portal` path is our own 404 (the same for everyone), staff get the app, a client gets the 403 body at `/workspace`, and
the portal works with both presenters. The presenter switch is the site config `cc_portal_spa` (`0` = the
server-rendered portal, D-121). **Frappe caches site config for 60 seconds per worker**, so a switch shows within a
minute (the check waits for it); restart `backend` to apply it at once. By default the check reads the portal under
the presenter the site uses and changes nothing. With `BOTH_PRESENTERS=1` it also switches to the other presenter for
about two minutes and then puts back the value it found: run that only before go-live or in a maintenance window.

## 4a. Outgoing mail (D-103: the company's email over SMTP)

Set up in the browser, as a System Manager: **Desk → search "Email Account" → New**.

1. Email Address: the sending mailbox, for example `projects@example.com`. Tick **Enable Outgoing** and **Default
   Outgoing**; leave Enable Incoming off.
2. Login and password of that mailbox. Use an **app password** for Google Workspace (2-step verification on); for
   Microsoft 365, SMTP AUTH must be allowed for the mailbox.
3. SMTP server and port: Google `smtp.gmail.com`, Microsoft 365 `smtp.office365.com`, port **587** with
   **Use TLS**, or your provider's values.
4. Save. Frappe signs in to the SMTP server on save and says so if the login fails. The password is stored
   encrypted with the site's key, which every backup set carries.

To try it, invite a test client from a project (Clients menu): the invitation mail must arrive. Sent and failed
mails are listed under **Email Queue**.

## 5. Backups

- The `backup` service takes a set at start and every `BACKUP_EVERY_HOURS` (24), keeping `BACKUP_KEEP` (14) sets
  in `BACKUP_DIR`: database, public and private files, the frozen approval copies (`approvals.tar`, the site's
  `private/cc_approvals` folder), the site config (with the encryption key), the Document Server's data, and
  `SHA256SUMS`. A set is published only when every part reads back; a failed run keeps the
  existing sets. Sets are private (folder 700, files 600).
- **Off-host copies (P2-01, D-107).** After each set, the `backup` service copies it to `OFFSITE_DIR` (the NAS),
  checks it there against its checksums, and only then names it a set. On the NAS it keeps sets for the number of
  days set in **Desk → Backup Settings → Keep copies for (days)** (default 30; the newest set always stays). Desk
  shows the last copy's result (OK or FAILED, the set, the time, a message). A failed copy never touches the sets on
  the server. Copies can be switched off there too (Desk then shows DISABLED); the readiness check then fails, on
  purpose. **After a failed copy** (Desk shows FAILED, `check-offsite.sh` lists the set as missing): fix the cause
  (usually the NAS mount, §10.5), then copy that set again:
  `docker compose --env-file … -f deploy/compose.yml exec backup bash /usr/local/bin/cw-backup.sh --copy <set>`.
  The NAS never keeps fewer than 7 sets (`OFFSITE_MIN_SETS`), whatever the dates say. A set is removed
  there only when both the date in its name and its folder's time are older than the setting.
- The sets hold the encryption key and every client file: keep the NAS share private (§10.5).
- **Restore drill, monthly and after every upgrade:**
  `CW_ENV_FILE=... bash deploy/restore.sh --drill <BACKUP_DIR>/<set>` restores into a throwaway stack, checks a
  staff login, every file's bytes, the frozen approval copies (each file's SHA-256 equals its name, and every file
  of the archive is back) and the encryption key, and restores the Document Server's data, then removes the
  throwaway stack. A set made before `approvals.tar` existed still restores; the drill says it has none. The
  result goes to `<BACKUP_DIR>/restore-drill.txt`; the readiness check wants one from the last 35 days. A set whose
  checksums do not match is refused before anything is restored.

## 6. Disaster recovery

On a new server: steps 2 and 3 with the same settings (the same `SITE_NAME` and secrets), copy the backup set
back, then `CW_ENV_FILE=... bash deploy/restore.sh --into-live <set>`; it restarts the stack. Point DNS at the new
server; Caddy gets a new certificate on its own.

Run `restore.sh` as root on a Linux host: the backup sets are root-only.

Restoring over a site that exists (going back to an earlier set) needs `--confirm-overwrite`: the script then takes
a safety backup of the current site and stops the app services while it restores.

## 7. Upgrades

A change is a new image, never an install into a running stack (DR-1): update the pins, `verify-pins.sh`,
`build.sh`, run the full test suite on `core`, take a backup, then `up -d` with the new `APP_IMAGE` and run
`init-site.sh` (it migrates). Run the readiness check again.

## 8. Health and logs

- `docker compose ... ps`: every service `running`, with `healthy` where it has a check (proxy, db, backend,
  frontend, backup, documentserver).
- `docker compose ... logs -f backend frontend websocket documentserver`.
- Office editing: a save that fails is kept by the Document Server and recovered at the next close (D-101).

## 9. Known limits of the MVP deploy

- The ONLYOFFICE 9.4 Community connection limit is reported as unlimited but has not been tried above 20 concurrent
  editors; do that on the production-sized server before relying on it (`cc_office_max_editors` can cap editing).
- Single server, no high availability; the restore drill is the recovery plan.
- On the local staging stack (`staging.localhost`) the backend cannot reach its own public address, so pictures
  in printed PDFs do not load there; on a server with real DNS they do.

## 10. On-premise server (D-103, D-106, D-107)

1. **Hardware.** 4 or more CPU cores, 16 GB RAM, a 200 GB SSD, on a UPS. Ubuntu Server 24.04 LTS.
2. **Software.** Docker Engine with the compose plugin (docs.docker.com, "Install Docker Engine on Ubuntu"). Firewall:
   `ufw allow 80,443/tcp`, SSH only from the office network, `ufw enable`.
3. **Router.** A fixed public IP from the internet provider. Forward TCP 80 and 443 to the server's LAN address
   (give the server a fixed LAN address too). Inside the office, the site name must also reach the server: turn on
   the router's NAT loopback ("hairpin"), or add a local DNS entry for the site name that points at the LAN address.
4. **Name and certificate.** At the company's DNS provider, an A record: `projects.<company>.com` → the public IP. In
   the settings file, `SITE_NAME=projects.<company>.com` and `TLS_ISSUER=<an IT email>`. Caddy gets the Let's
   Encrypt certificate over port 80 on first start and renews it on its own. Check from outside the office
   (a phone on mobile data): `https://projects.<company>.com` opens with a valid lock.
5. **NAS (SMB share).** The sets hold the database, every client file and the encryption key, unencrypted.
   - **On the NAS:**
     - A share for these backups, reachable only by one account that only this server uses. No guest access, and
       no other users or groups on its access list.
     - Turn on **snapshots** (or a recycle bin) for the share, kept by the NAS itself and **not deletable by that
       account**. The share is mounted read-write, so malware on the server, or a mistaken "keep 1 day", could
       otherwise erase every copy.
     - Turn on **volume encryption** on the NAS if it offers it.
     - Keep a **copy outside the building** too: a second NAS elsewhere, or the NAS's own cloud sync. A NAS in the
       same office does not survive fire or theft (the 3-2-1 rule).
   - **On the server:**
     ```bash
     sudo apt install cifs-utils
     sudo install -d -m 700 /etc/construction-workspace /mnt/nas/construction-workspace
     sudo install -m 600 /dev/null /etc/construction-workspace/nas.cred   # then write: username=… password=…
     # /etc/fstab (one line): SMB 3.1.1 with encryption (seal), no client cache, root-only on this server:
     # //<nas-address>/<share> /mnt/nas/construction-workspace cifs credentials=/etc/construction-workspace/nas.cred,vers=3.1.1,seal,cache=none,uid=0,gid=0,file_mode=0600,dir_mode=0700,_netdev,nofail 0 0
     sudo mount -a && findmnt /mnt/nas/construction-workspace           # must show cifs and seal
     sudo touch /mnt/nas/construction-workspace/.cw-offsite-target       # ONLY while mounted: marks the share itself
     ```
   - `OFFSITE_DIR=/mnt/nas/construction-workspace` in the settings file. Sets go to
     `<share>/<SITE_NAME>/<set>`, so two stacks never prune each other's sets.
   - **If the NAS is not mounted** (it is down at boot, or the password has changed), the folder underneath has no
     marker file. The copy then fails with FAILED in Desk, nothing is written to the server's own disk there, and
     the server's sets are kept. Never create the marker without the share mounted.
   - **NFS instead of SMB:** only with `sec=krb5p` (Kerberos encryption); plain NFS sends every client file
     unencrypted over the network, and `check-offsite.sh` refuses it.
   - **Once, on the real NAS:** run one backup (`docker compose … exec backup bash /usr/local/bin/cw-backup.sh`) and
     `check-offsite.sh`. The copy keeps timestamps only, never Linux owners, which an SMB share may refuse.
6. **Then §2–§4**: settings file, build and start, `init-site.sh`, the check account, `check-staging.sh` and
   `check-offsite.sh`. In Desk → Backup Settings, choose how many days the NAS keeps.
7. **The 21+-editor run (Q-05, D-107).** On this server, before relying on more than 20 people editing office files
   at once: open the same `.docx` in 21 browser sessions (21 staff accounts, or private windows), type in each, and
   check that every session saves (each one's edits appear after a reload). If session 21 is read-only or does not
   save, set `cc_office_max_editors` to 20 in the site config (`bench --site … set-config cc_office_max_editors 20`):
   extra editors then open read-only with a notice (D-082).

### The project map (P3-09, D-138, D-157)

The dashboard's map shows each project that has a site location (Desk → the project → *Site location*: place,
latitude and longitude; staff only). Leave the location empty for a confidential project. The map's background comes
from OpenStreetMap's public tiles, so the office server needs internet. OpenStreetMap sees each viewer's IP address,
the site's web address and the area viewed, never project data (D-157). To use another source or turn the map off:
`bench set-config -p cc_map_tiles '{"url": "https://<tiles>/{z}/{x}/{y}.png", "attribution": "© <source>"}'`, or
`bench set-config cc_map_tiles off`. A source without https, the three placeholders or an attribution shows no map.

## 11. Onboarding (P3-12…P3-22)

Below, `bench` means `docker compose --env-file /etc/construction-workspace/stack.env -f deploy/compose.yml exec
backend bench --site <SITE_NAME>`. Accounts come only from invitations: sign-up is off, and so are Frappe's own
invitations and sign-in by email link (D-204).

### 11.1 Mail first

Invitations, codes, reset emails and two-step setup all go by email. Set up outgoing mail (§4a) before inviting
anyone. Without it, Settings and the People page say so, and invitations pause (D-192). Failed onboarding mails are
deleted after a day, so their links never wait in the Email Queue (D-223, D-239).

### 11.2 Inviting a client

In the project's **Settings → Client contacts → Invite contact** (a Construction Manager of the project):

- **With an email:** the link is emailed and works for 7 days. The link in that email opens with no code. A link
  copied from the screen, or the QR code, asks for a 6-digit code sent to that email.
- **Without an email:** an open link for a chat or a QR code, for 3 days. Each person types their email, proves it
  with a code and waits; Approve or Decline them under **Waiting for you**. With two or more managers on the project,
  the one who made the link does not approve its people. An approved person gets their own 48-hour link by email.
- **New link** makes a new link and kills the old ones; **Cancel** stops it at once.

### 11.3 The People page (System Managers)

Account menu → **People**. Invite a team member (Construction Manager or Construction Staff, and a project); they join
through the same join page. Under **Manage**: change the role, the projects, send a password reset email, switch off
two-step sign-in for a lost phone, or turn access off (they are signed out everywhere at once and their invitations
stop). Administrator and System Managers show "Managed in Desk" and are never changed here (D-189).

Use a named System Manager account day to day. Keep **Administrator** for emergencies, with a real mailbox.

### 11.4 A locked account

More than ten wrong passwords in a row (the eleventh) lock an account for 60 seconds (System Settings: *Allow Consecutive Login Attempts*,
*Allow Login After Fail*). Wait a minute. Many people behind one office router share one address, so a burst of
wrong passwords can delay everyone for that minute.

### 11.5 Two-step sign-in

- **Each person's choice:** account menu → **Two-step sign-in**: the password, scan the QR code with an
  authenticator app (Google or Microsoft Authenticator), enter the code. Turning it off needs the password and a
  current code. Admins are urged to turn it on (D-190).
- **Required:** a System Manager who has set it up for their own account can require it of the team or of everyone
  on the People page. Whoever has not set it up gets a setup link by email at their next sign-in, so outgoing mail
  must work (D-231, D-233).
- **Lost phone:** People → Manage → *Switch off two-step sign-in*. For a System Manager (the People page never
  changes one), from the console: `bench execute construction_core.accounts.two_step.reset_for --args '["<account>"]'`.
- **The way back** when mail fails under a requirement, or Administrator cannot sign in:
  `bench execute frappe.db.set_default --args '["cc_two_step_required", "nobody"]'`, then
  `bench execute construction_core.accounts.two_step.setup` (`bench execute` commits).
- Redis holds a password for up to 3 minutes during a two-step sign-in (Frappe's design): keep the Redis containers
  on the stack's private network only, as `deploy/compose.yml` has them (D-229).

### 11.6 Privacy requests (Data Privacy Act 2012)

Requests come by email to the privacy contact (`bench set-config cc_privacy_email privacy@example.com`); Frappe's own
request forms are off (D-197). The join page shows the notice approved in R-13 (version in
`onboarding/privacy.py`). To see what we hold: Desk → Client Profile, and the person's invitations (Access Invite).
To erase our onboarding records of a person (their client record, invitations and requests):
`bench execute construction_core.onboarding.privacy.erase --args '["<email or account>"]'` (`bench execute` runs as
Administrator and commits). Their name and email stay in the project records (D-193). Turn their account off
on the People page, or delete it in Desk.

### 11.7 Retention (the daily job)

The scheduler runs `onboarding.jobs.daily` every day, catching up after a missed day (D-239): invitations that ended
without anyone joining are deleted 30 days after; declined requests and approvals that ran out go after 30 days; a
client's mobile and company are cleared 2 years after they leave their last project. The scheduler must run
(`bench scheduler status` must say enabled; go-live checks it, §12).

### 11.8 When mail is down and someone must start now

- **A team member:** Desk → User → New, with the role Construction Manager or Construction Staff, then **Set New
  Password** on the user, and add them to projects on the People page. Tell them the password in person and ask them
  to change it (account menu → Change password).
- **A client:** wait for mail if you can: an account made by hand records no consent. If not, a System Manager runs
  `bench execute construction_core.clients.add_client --args '["<project>", "<email>", "<full name>"]'` and sets the
  password in Desk as above.

### 11.9 Approval evidence (P3-81)

- **Daily digest.** Every day the site mails the evidence mailbox the head (position and hash) of every project's
  approval chain. The mail has an attachment `heads.json`. Save it **outside the server** (a mail folder or a USB
  drive); a copy on the server proves nothing.
- **Restore drill with the heads.** Add `--heads <file>` to the drill (§5): `bash deploy/restore.sh --drill <set>
  --heads heads.json`. It checks the restored chain against those heads and fails if one is missing or any check
  fails. Use the last file mailed **before** the set was taken: a later one names events the set does not hold.
- **Evidence pack** for one project (on demand or at project close):
  `bench --site <site> execute construction_core.approvals.pack.export --kwargs '{"project": "<project>"}'`.
- **End of service** (a firm leaves): `bench --site <site> execute construction_core.approvals.pack.end_of_service
  --kwargs '{"dest": "<folder>"}'` writes one pack per project, with the personal detail; hand the packs
  over, then delete the site yourself. Write down the date, the firm and who did it in your own log: it is outside the chain.
- **Legal hold.** `bench --site <site> execute construction_core.approvals.retention.legal_hold --kwargs
  '{"request": "<request>", "on": 1, "reason": "<why>"}'` stops the clearing of that request's personal detail; `"on": 0` lifts it.
  Both are chain events.
- **Erase requests.** `privacy.erase` keeps approval evidence, records an `erase_request_received` event and mails the
  person what was kept and why (Data Privacy Act Sec 11(e)).

## 12. Go-live (P3-10)

Follow these steps in order on the office server. Every check prints one line per item, `PASS` or `FAIL`, and the
last line is `OK: 0 failure(s)` or `FAILED: n failure(s)`. Do not go live with a FAIL. The settings file is the one
from §2; below it is `/etc/construction-workspace/stack.env`.

### 12.1 Before the first start

1. **The server** (§10): Linux, Docker, the NAS share mounted (§10.5), the domain's DNS pointing at the office's
   public address, ports 80 and 443 forwarded to this server only.
2. **The clock.** Turn on time sync (`timedatectl set-ntp true`, or chrony) and check that `timedatectl` shows
   `System clock synchronized: yes`. Approval records and sign-in codes depend on the time.
3. **The settings file** (§2), plus:
   - `COMPANY_NAME` and `PRIVACY_EMAIL`: the firm's name and the address that receives privacy requests (D-218).
     `init-site.sh` writes them to the site config. The owner can change them later in the set-up wizard; the
     wizard's values then win.
   - `EDGE_SUBNET`, only if `198.18.240.0/28` is in use anywhere on the office network (rare: it is a reserved range).
     This is the network between the proxy and the web server. The web server believes a client address only from it.
4. **Build, start, create the site** (§3): `deploy/build.sh core+office`, `docker compose ... up -d`, then
   `deploy/init-site.sh`. `init-site.sh` also sets `host_name` (the public address, with the port if it is not 443),
   hides tracebacks and sets Allowed File Extensions. The list holds the types the app works with (office, PDF,
   images, CAD and BIM models, MS Project `.mpp`, MicroStation `.dgn`, Google Earth `.kmz`, audio, video, ZIP, mail) and
   never `.html`, `.svg` or `.js`. It applies to every upload, staff uploads too. `.7z` and `.rar` stay refused (the
   owner, 2026-10-26); if the team needs another type, add it in Desk
   (System Settings → Allowed File Extensions), never one of those three.

### 12.2 Set-up by people

1. **Mail** (§4a, §11.1): the company's outgoing account, confirmed by its code on the Mail step of the set-up
   wizard. No **Always BCC** on it.
2. **The owner finishes the set-up wizard** (`/workspace` as a System Manager): company name, privacy contact,
   two-step sign-in, the first project. Every step must be done or skipped.
3. **Portal approvals** (approvals design §4.7, D-431) stay off until the site config `cc_approvals_enabled` is set
   (`docker compose exec backend bench --site <site> set-config -p cc_approvals_enabled 1`). The daily evidence job exists (P3-81). Before you
   turn approvals on, the owner sets and confirms the evidence mailbox (Approvals settings), and someone saves the
   daily `heads.json` outside the server (§11.9).

### 12.3 The checks

The check account signs in with a password only. Run the checks **before** anyone requires two-step sign-in (the
wizard's Security step, or People): if the requirement is already on, set it to "nobody" for the checks and back
afterwards, and say so in your log. check-golive runs again after the wizard is finished.

```bash
export CW_ENV_FILE=/etc/construction-workspace/stack.env
bash deploy/verify-pins.sh       # the image's pins
bash deploy/seed-check.sh        # once: the check accounts (§4)
bash deploy/check-staging.sh     # §4: TLS, ports, sign-in, services, backups, scanner
bash deploy/check-offsite.sh     # §5: the copy on the NAS
bash deploy/check-routes.sh      # §4: routes, every public page and its Permissions-Policy (check-public.sh)
bash deploy/check-golive.sh      # the go-live settings (§12.4)
```


After the checks pass, turn off the two check accounts (People → Access off for the check team member; remove the check client from the "Staging check" project) so no standing login stays on the live site.

### 12.4 What each check-golive FAIL means

| Line | What to do |
|---|---|
| the proxy is the only way in | A service other than `proxy` publishes a port, or the proxy publishes more than 80 and 443. Remove the extra `ports:`. |
| nginx trusts X-Forwarded-For from the edge network only | The frontend's `UPSTREAM_REAL_IP_ADDRESS` is not the edge network's subnet. Use `deploy/compose.yml` as shipped and recreate the stack (`down`, then `up -d`; volumes are kept). |
| the edge network holds the proxy and frontend only | Another container joined the `edge` network. Remove it. |
| the Document Server's container cannot reach backend:8000 | The backend listens on every network. It must use the `command:` in `deploy/compose.yml` (gunicorn on the `cc-backend` address only). |
| forged-header | A forged client address from inside the stack was believed. Fix the two lines above. |
| the scheduler service is running / scheduler | Run `docker compose ... up -d scheduler` and `bench --site <site> scheduler enable`. Remove `pause_scheduler` and `disable_scheduler` from the site config. |
| no mail catcher / mail-account | Mail goes to a test catcher or to a stack name. Set the company's SMTP server (§4a). |
| mail-confirmed | The outgoing mail account changed after its code was confirmed, or was never confirmed. Confirm it again on the Mail step. |
| always-bcc | Clear **Always BCC** on the outgoing Email Account: a copy of every invitation and code would go to that address. |
| the backend is not Frappe's development server / tracebacks | Remove `DEV_SERVER` and `developer_mode`. Turn off **Allow Error Traceback** in System Settings. |
| pins | A sign-in setting of D-197 changed in Desk (the line names it). Run `bench --site <site> migrate`: every migrate puts these back. |
| two-step | Two-step sign-in is off, or a role other than the opt-in and the required ones has the two-factor flag. Run `bench --site <site> execute construction_core.accounts.two_step.setup`. |
| session-expiry | System Settings → Session Expiry must be `72:00`. Run `bench --site <site> execute construction_core.accounts.sessions.pin_session_expiry`. |
| allow-tests | Remove `allow_tests` from the site config. |
| social-login | Disable every Social Login Key. Sign-in is by password and two-step only. |
| setup-finished | The owner has not finished the set-up wizard (§12.2). |
| company-name / privacy-contact | Neither the wizard nor `COMPANY_NAME` / `PRIVACY_EMAIL` sets it (§12.1). |
| time-zone | Set System Settings → Time Zone. |
| host-name | `host_name` is not `https://<domain>`. Run `init-site.sh` again. Mail links and the logo in mail use it. |
| file-extensions | Allowed File Extensions is empty, allows `.html`, `.svg` or `.js`, or refuses a type the app works with (the line names it). Run `init-site.sh` again: it adds the app's types, keeps types added in Desk and takes out those three. |
| approvals-daily-job | The approvals daily job is missing or stopped. Run `migrate`, then Desk → Scheduled Job Type → `digest.daily` → clear **Stopped**. |
| approvals-flag | Portal approvals are on, but the evidence mailbox is not confirmed (§12.2). |
| approvals-verify | The approval records do not verify. Stop, keep the server as it is and call the developer. |
| the server clock matches the reference clock | The clock is more than 5 seconds off the reference (`TIME_REFERENCE`, default the Date header of https://www.cloudflare.com), or the internet line is down. |
| the host keeps its time synchronised | Turn on time sync (§12.1). |

### 12.5 Notes for the IT person

- **Location and the microphone need HTTPS.** A client's location on an approval and a voice note work only over the
  public `https://` address, never over a plain `http://` LAN address. The Permissions-Policy header allows the
  microphone on the app's pages, location on the portal only, the camera nowhere (Take photo uses the file picker),
  and none of them on `/office/` and the vendored viewers. `check-public.sh` checks each one.
- **Hairpin NAT.** When an office user opens the public address from inside the office, the router can loop the
  traffic back, and the site then records the router's address, not the user's. Approval records show that address.
  For true addresses inside the office, use split DNS: the domain resolves to this server's LAN address there.
- **Chat limits** (discussion design §7, D-179, D-182, `client_files.py`). Clients: 30 file sends in 10 minutes, and 50
  files and 1 GiB per project per day, shared by that project's clients. Staff: 60 chat uploads in 10 minutes, no daily cap. Up to 10 files in
  a message, two uploads at a time; a voice note is at most 5 minutes and 10 MB. A client at the cap sees "You can
  send more files tomorrow" and can still write.
- **Unsent files are deleted.** A file uploaded to a chat but never sent is deleted 24 hours after the upload, by the
  hourly job (so the scheduler must run). It is a real delete, not the bin: the file never became part of the
  project's record (D-389).
- **Disk for voice notes and photos.** A voice note is about 0.5 MB a minute (at most 10 MB). A phone photo is shrunk
  to 2048 px, about 0.5 to 1 MB; "Send original quality" keeps the full picture, often 3 to 8 MB. Each chat image also
  gets a preview of about 30 KB. Example: 20 active projects, each with 10 photos and 5 one-minute voice notes a
  working day, use about 20 × (10 × 1 MB + 5 × 0.5 MB) = 250 MB a day, about 65 GB a year. The backups (§5) keep 14
  local sets and the NAS keeps more, so give the backup disk several times the site's size. Measure the real figure
  with `du -sh` on the `sites` volume after the first month.
