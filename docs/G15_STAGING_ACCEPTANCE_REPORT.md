# G15 — STAGING DEPLOYMENT / ACCEPTANCE REPORT · 2026-10-08

## Verdict: **BLOCKED_OWNER — no staging host was provided; nothing was deployed.**

| | |
|---|---|
| STAGING HOST IDENTITY | **NOT PROVIDED** — the brief carried placeholders (`<IP_OR_HOSTNAME>`, `<SSH_USER>`, `<STAGING_DOMAIN_OR_NONE>`, `<DEPLOY_PATH>`). Per §2 ("if host identity is ambiguous: STOP before modifying server") no remote system was touched. |
| Session capability | this build container has no `ssh`/`scp`/`rsync` binaries; a remote deploy must be run from the owner's workstation or on the host itself (`scripts/staging/deploy.sh` is host-side). |
| DEPLOY SHA | `474f7d84d2c64938ce86ca74fdb33cc0c0c7f2ae` (`origin/develop`, pinned in `docs/G15_DEPLOY_RECORD.md`) |
| MAIN SHA | `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` (untouched) |
| DATE | 2026-10-08 |
| CONTAINERS / PORTS / DOMAIN / TLS | not applicable — not deployed. Planned: project `vip-customs-ai-staging`; postgres · migrate · api · web · caddy proxy; only proxy publishes `${PUBLIC_HTTP_PORT:-80}` / `${PUBLIC_HTTPS_PORT:-443}`; TLS per `TLS_MODE` (IP-only → `TLS_PENDING / IP_ACCEPTANCE`). |
| MIGRATION HEAD (expected) | `0010_copilot_meta`, single head (enforced by `scripts/staging/deploy.sh`) |
| HEALTH / READY / FRONTEND / ACCEPTANCE / NEGATIVE / RESTART / BACKUP-RESTORE / PERFORMANCE on staging | **NOT RUN** (no host) |

## What G15 produced instead (all committed, no secrets)
- `docs/G15_DEPLOY_RECORD.md` — the exact SHA to deploy; never a floating tree.
- `scripts/staging/deploy.sh` — host-side, idempotent: identity + inventory (stops nothing), dedicated checkout reset to `DEPLOY_SHA`, `.env` guard (required keys, `chmod 600`, `IMAGE_TAG` = SHA), previous-image + `pg_dump` baseline (`FIRST_DEPLOY=YES/NO`), `build --no-cache`, `up -d`, `alembic current/heads`, in-container `/health` `/ready`.
- `scripts/staging/acceptance.sh` — client/host-side: external health + TLS/redirect check, demo seed, Playwright, HTTP flow A–P (`scripts/acceptance_http.py`), negative tests (`scripts/staging/negative_tests.py`), demo-label notice, light performance smoke, `restart` + `down/up` persistence, `pg_dump` + restore into a temporary DB, log/secret review. Writes `artifacts/test-results/staging-acceptance.txt`.
- `infra/staging/docker-compose.staging.yml` — `config` validated with a throwaway env (images tagged by SHA, only the proxy publishes ports, required variables enforced: missing `PUBLIC_WEB_ORIGIN`/`POSTGRES_DB` fail interpolation); per-service `env_file` made optional so validation works before the host `.env` exists.

## Local dry-run of the staging automation (evidence that the scripts work end-to-end)
Target: the G14 Docker stack on this machine (`infra/docker-compose.yml`, images built from `474f7d8`), i.e. the same containers a staging host would run, minus the Caddy proxy/TLS.

Evidence file: `artifacts/test-results/staging-acceptance-dryrun-local.txt` (final run 2026-10-08 09:58 UTC, exit 0).

| Section | Result |
|---|---|
| 1. external health | `/health` 200 · `/ready` 200 (`migrations=0010_copilot_meta`, `ai_provider=mock`) · frontend 200 · TLS: `TLS_PENDING / IP_ACCEPTANCE` (plain-http local target, reported, not faked) |
| 2. seed (host side, inside api container) | tenant DEMO, 4 users (passwords rotated to the run's `SEED_DEMO_PASSWORD`), 4 demo datasets, case VIP-HQ-261008-001 |
| 3. Playwright (browser) | **1 passed** — login → 9 V12 nav entries → seeded case BLOCKED → Goods CT-88 8537 BLOCKED → Copilot → release gate BLOCKED → declaration |
| 4. HTTP acceptance A–P | **17/17 PASS** (G reported `item1=0.92 item2=0.99 item3=0.69` with `history={1,2,3: True}` = the +0.05 approved-memory boost on a re-used DB; 0.87/0.95/0.64 hold on an empty DB as in G14) |
| 5. negative / security | **18/18 PASS** — invalid/tampered token, wrong password → 401; operator cannot approve HS / resolve issues / mark READY / export release → 403; traversal filename sanitised; `.exe` → 422; unknown doc_type → 422; 21 MB → 413; open issues block READY/release → 409; unknown ids → 404; admin has no customs permission; audit actor/before/after + chain valid |
| 6. demo labels | `/knowledge/notice`: `demo_active=true`, "DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING", 4 datasets listed |
| 7. performance (5 sequential requests each) | /health 4 ms · /ready 6–8 ms · /api/v1/cases 4–5 ms · /dashboard/summary 4–12 ms · /knowledge/datasets 4–7 ms |
| 8. restart / persistence | `compose restart`: ready 200, cases 11→11 · `down` + `up -d` (volumes kept): ready 200, cases 11, uploads 35 files · restart counts 0/0/0 |
| 9. backup / restore | `pg_dump -Fc` 252,630 bytes; restored into temporary DB `restore_test`: cases=11, audit_events=638; live DB untouched; temp DB dropped |
| 10. log / secret review | 24 lines, 0 error/traceback/restart; 0 secret-pattern hits; seed password absent |

Defects found by the dry-run and fixed in this gate: `compose()` helper used `eval` (broke container-side quoting); `seed_demo.py` did not rotate
existing demo passwords; Playwright/HTTP checks assumed an empty database (now accept the documented +0.05 history boost only when `history_refs`
exist) and the spec now selects the seeded case explicitly; a DB dump had been committed by accident and was untracked (`backups/` ignored).

## Owner inputs required to execute G15 (then re-run this gate)
1. Staging host reachable over SSH (or shell on the host): hostname/IP, SSH user, confirmation it is **not** production.
2. `DEPLOY_PATH` (default `/opt/vip-customs-ai`).
3. Domain or "none" → `PUBLIC_HOST`, `PUBLIC_WEB_ORIGIN`, `TLS_MODE` (`acme` with public DNS, `internal` self-signed, `off` behind an upstream terminator).
4. Secrets generated on the host into `infra/staging/.env` (`docs/STAGING_SECRETS.md`): `POSTGRES_PASSWORD`, `APP_SECRET_KEY`, optional `SEED_DEMO_PASSWORD`.

Exact commands once inputs exist (on the host):
```bash
ssh <SSH_USER>@<HOST> 'hostname; whoami; docker version --format {{.Server.Version}}; docker compose version --short; df -h /; free -h'
# on the host
git clone https://github.com/thanhbn123/vip-cutoms-ai.git /opt/vip-customs-ai && cd /opt/vip-customs-ai && git checkout 474f7d84d2c64938ce86ca74fdb33cc0c0c7f2ae
cp infra/staging/.env.staging.example infra/staging/.env && $EDITOR infra/staging/.env && chmod 600 infra/staging/.env
DEPLOY_SHA=474f7d84d2c64938ce86ca74fdb33cc0c0c7f2ae DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deploy.sh
BASE_URL=https://<PUBLIC_HOST> WEB_URL=https://<PUBLIC_HOST> SEED_DEMO_PASSWORD=… PW_CHROMIUM_PATH=… \
  COMPOSE="docker compose -p vip-customs-ai-staging -f infra/staging/docker-compose.staging.yml --env-file infra/staging/.env" bash scripts/staging/acceptance.sh
```
(IP-only staging: use `http://<IP>` and record `TLS_PENDING / IP_ACCEPTANCE`; self-signed: add `E2E_INSECURE_TLS=1` for the test clients only.)

## Bugs / blockers
Bugs found in this gate: none in application code (one robustness fix to the staging compose `env_file`). Blockers: B-03 staging host/TLS/secrets (owner).


## G15B (2026-10-09) — real staging deployment attempt: **BLOCKED_ENV — not executed, nothing deployed**

Inputs now provided: host `160.22.170.20`, user `root`, domain `hq.vipgroup.com.vn`, path `/opt/vip-customs-ai`, DEPLOY_SHA `bfc82cb45cf40453a14208a43fef4660fcc1f067`.

| Check (from the build session) | Result |
|---|---|
| Git rebaseline | origin/main `2afdf6b…` ✓ · origin/develop `bfc82cb…` ✓ (no drift) |
| DNS | `hq.vipgroup.com.vn` → `160.22.170.20` ✓ (DNS_PENDING = NO) |
| SSH client | installed in-session (OpenSSH 9.6p1) |
| SSH reachability | **direct `tcp/22` → connection timed out; via egress proxy CONNECT → connection closed (policy)** |
| SSH credential | **none available** (no key in `~/.ssh`, no password supplied to the session) |
| HTTPS to the domain / IP | `https://hq.vipgroup.com.vn/` → no connection (000); `http://160.22.170.20/` → 403 from the egress proxy — host not in the environment's allowed network set |
| Host identity, inventory, build, start, migration, health, TLS, acceptance, Playwright, negative, restart, persistence, backup, restore, logs, performance | **NOT RUN** — would require claims without remote evidence (§ "DO NOT claim PASS without real remote evidence") |

What this gate produced: `docs/G15B_OPERATOR_RUNBOOK.md` — the exact command sequence (sections 2–26 of the brief) using the committed
`scripts/staging/deploy.sh` and `scripts/staging/acceptance.sh`, runnable from any machine with SSH to the host. The acceptance script accepts an
`ssh … docker compose …` prefix in `COMPOSE`, so the whole suite can be driven remotely from a workstation.

Remediation to run G15B from a Claude cloud session: allow outbound access to `160.22.170.20` (and `hq.vipgroup.com.vn`) in the environment's
Network access settings, and provide an SSH key for `root@160.22.170.20` through the environment's secrets. Even then, port 22 must be permitted by
the egress policy; HTTPS-only policies will still block SSH.
