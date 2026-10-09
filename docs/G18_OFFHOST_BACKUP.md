# G18 — OFF-HOST BACKUP DESIGN

Status: **scripts and units prepared; destination, credential and retention are OWNER INPUTS.** Marked
`PROPOSED_OWNER_APPROVAL_REQUIRED` where noted. Nothing has been configured on any host.

## 1. Today

`scripts/production/backup.sh` (G16) writes a nightly `pg_dump` + uploads archive + checksums + manifest to
`BACKUP_DIR` on the **same host**, mode 0600, retention `BACKUP_RETENTION_DAYS`. A host loss loses the backups.

## 2. Design

```
02:30  vip-customs-backup.timer          → backup.sh          local pair in BACKUP_DIR (unchanged)
03:15  vip-customs-backup-offsite.timer  → backup_offsite.sh  verify checksums → encrypt (age) → upload → prune → status JSON
       /ready (APP_MODE=full)             reads BACKUP_STATUS_FILE; stale/missing → 503 (blocking: "backup status …")
```

`scripts/production/backup_offsite.sh`:

| Step | Behaviour |
|---|---|
| configuration | from the production env file: `OFFSITE_METHOD` (`rclone` \| `ssh`), `OFFSITE_TARGET`, `OFFSITE_ENCRYPT_RECIPIENT`, retention counts, `BACKUP_STATUS_FILE`; **exit 3 while the destination is unset** (owner input) |
| integrity | re-verifies the local `.sha256` of the newest `db-*.dump` and `uploads-*.tgz`; a mismatch is **not** replicated (exit 1) |
| encryption | `age -r <recipient>` for both artifacts **before** upload; plaintext off-host refused (exit 4) unless `OFFSITE_ALLOW_PLAINTEXT=yes` is set deliberately |
| upload | `daily/<stamp>/`; also `weekly/` on Sundays and `monthly/` on the 1st (GFS) |
| retention | prunes remote `daily/weekly/monthly` beyond the counts (rclone); ssh method prints the prune instruction |
| status | writes `BACKUP_STATUS_FILE` (`last_success_at`, `destination_kind`, `offsite`, `encrypted`, artifacts, prefixes) **only on success**, mode 0600, atomic rename |
| secrets | never prints the env file; the rclone credential lives in the deploy user's rclone config (0600), the age private key **never** on the production host |

Tests: `tests/test_g18_production_prep.py` (refuses without destination, refuses plaintext, refuses corrupt
artifacts, encrypts + uploads + prunes + writes status with a mocked rclone/age, fails without a local pair).

## 3. Proposed defaults — PROPOSED_OWNER_APPROVAL_REQUIRED

| Item | Proposal |
|---|---|
| cadence | daily (after the 02:30 local backup) |
| retention | **daily 7 · weekly 4 · monthly 6** (`OFFSITE_RETENTION_*`) |
| encryption | age, recipient = owner-held key pair; private key stored offline (password manager + printed copy), not on any server |
| destination | object storage in a different provider/region from the production VPS (rclone remote), or a second owner-controlled host via ssh; **owner chooses** |
| local retention | keep `BACKUP_RETENTION_DAYS=14` for fast restores |
| restore verification | monthly drill: download newest pair from off-site, `age -d`, restore into a scratch PostgreSQL + scratch uploads dir, run `scripts/acceptance_http.py` against a scratch stack; record in `PRODUCTION_RUNBOOK.md §4` log |
| alert | `vip_backup_age_hours > 26` (from `/metrics`) and systemd unit failure → notification destination (owner input) |

## 4. Restore (off-host copy)

1. `rclone copy remote:bucket/vip/daily/<stamp> ./restore/` (or scp).
2. `age -d -i <private key> -o db.dump db-*.dump.age` and the same for uploads; `sha256sum -c` against the copied `.sha256` files.
3. Follow `docs/PRODUCTION_RUNBOOK.md §4` (quiesce, `pg_restore`, untar uploads, reconcile, restart).

## 5. Consistency caveat (unchanged from G16)

The local pair is not an atomic snapshot (dump and tar seconds apart). The off-host copy inherits that. For an
exact point-in-time pair use the quiesced procedure or a VM/volume snapshot (an infrastructure choice under B-06).
