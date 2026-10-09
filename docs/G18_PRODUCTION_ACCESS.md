# G18 — PRODUCTION ACCESS MODEL (deploy permissions)

Principle: **production never requires unrestricted root SSH for routine operation.** Routine = deploy a pinned
SHA, run backups, read logs, run the B-07 script, rotate app secrets. Root is needed once, at provisioning, and
afterwards only for OS updates and systemd unit installation — by a named administrator, not by the deploy key.

## 1. Users

| Account | Purpose | Login | sudo | Docker |
|---|---|---|---|---|
| `root` | provisioning, OS updates, installing systemd units | SSH key only, password login disabled; consider `PermitRootLogin prohibit-password` → later `no` with an admin user | n/a | — |
| `deploy` | all routine operations | SSH **key only** (`PasswordAuthentication no`), one key per operator, keys revocable individually | **none** by default; optional minimal entries (see §3) | member of `docker` group (see §2) |
| application | `appuser` inside containers (already the case: Dockerfile `USER appuser`) | none | none | — |

Staging already uses `deploy@160.22.170.20`.

## 2. Docker access decision

Membership of the `docker` group is root-equivalent on the host (one can mount `/` into a container). This is
accepted for `deploy` **because** the host is dedicated to this product (option B in
`G18_PRODUCTION_INFRA_OPTIONS.md`) and the alternative (rootless Docker or sudo-wrapped compose) adds
operational friction without removing the trust in the deploy key. Consequences: the deploy key is a production
credential — stored in the operator's hardware key or password manager, rotated when an operator leaves.
If the owner chooses option A (shared host), rootless Docker or a sudo-restricted `docker compose` wrapper is
**required** instead, because the group would then grant access to other tenants' containers.

## 3. Minimal sudo (only if needed)

```
# /etc/sudoers.d/vip-customs-deploy  (mode 0440) — PROPOSED, install as root only if the owner wants
# deploy to (re)start the backup timers without root interaction
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart vip-customs-backup.timer, \
                           /usr/bin/systemctl restart vip-customs-backup-offsite.timer, \
                           /usr/bin/systemctl status vip-customs-backup*.service, \
                           /usr/bin/journalctl -u vip-customs-backup*
```
No wildcard shells, no `ALL`.

## 4. Paths and ownership

| Path | Owner | Mode | Notes |
|---|---|---|---|
| `/opt/vip-customs-ai` (checkout) | `deploy:deploy` | 755 dirs / 644 files | `scripts/staging/deploy.sh` resets it to the pinned SHA |
| `/opt/vip-customs-ai/infra/production/.env` | `deploy:deploy` | **600** | secrets; never committed |
| `BACKUP_DIR` (`/var/backups/vip-customs`) | `deploy:deploy` | **700**, artifacts 600 | enforced by `backup.sh` |
| `~deploy/.config/rclone/rclone.conf` | `deploy` | 600 | off-site credential (owner input) |
| Docker volumes (`pgdata`, `uploads`, `caddy_*`) | docker | — | backed up via the scripts / VM snapshot |

## 5. Network

Inbound: 22 (deploy + admin keys only; optionally restrict source IPs), 80, 443. Nothing else. PostgreSQL and
the API are not published on host interfaces (compose `internal` network). SSH: `PasswordAuthentication no`,
`PubkeyAuthentication yes`, `MaxAuthTries 3`, fail2ban or equivalent.

## 6. No unrelated service access

Dedicated host → nothing unrelated exists. The deploy user must not be reused for other projects, and its key
must not be added to other hosts.

## 7. Operations map (who runs what)

| Operation | Account | Command |
|---|---|---|
| deploy pinned SHA | deploy | `DEPLOY_SHA=… bash scripts/staging/deploy.sh` (+ production overlay, see `PRODUCTION_RUNBOOK.md §1`) |
| backup now | deploy | `bash scripts/production/backup.sh` / `backup_offsite.sh` |
| deactivate demo users (B-07) | deploy | `bash scripts/staging/deactivate_demo_users.sh --execute` |
| install/enable timers | root (once) | `systemctl enable --now …` |
| rotate `APP_SECRET_KEY` | deploy | edit `.env`, `docker compose up -d api` (all sessions log out) |
| OS updates / reboot | root/admin | scheduled window, after a backup |
