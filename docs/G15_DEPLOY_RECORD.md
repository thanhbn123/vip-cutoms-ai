# G15 DEPLOYMENT RECORD

Updated by **G15C — real staging deployment from the owner's local workstation (2026-10-09)**.
Full evidence: `docs/G15_STAGING_ACCEPTANCE_REPORT.md`.

## Current staging deployment (REAL)

| | |
|---|---|
| **FINAL DEPLOY SHA** | **`9649ec79db189857628ced0b11eaeaf6635fb42c`** |
| FINAL DEVELOP SHA | `9649ec79db189857628ced0b11eaeaf6635fb42c` (deployed SHA **equals** `origin/develop`) |
| MAIN SHA | `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` — **unchanged, not merged** |
| Host | `160.22.170.20` (`CIITNRVPlinux`, Ubuntu 26.04 LTS, 4 vCPU / 7.2 GiB / 89 GB) |
| Domain | `https://hq.vipgroup.com.vn` (DNS A → `160.22.170.20`) |
| Deploy path | `/opt/vip-customs-ai` (detached checkout, working tree clean) |
| Compose project | `vip-customs-ai-staging` |
| Migration head | `0010_copilot_meta`, single head |
| Providers | `AI_PROVIDER=mock` — intentional, for workflow acceptance |
| Knowledge data | DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING (`is_demo=true` only) |
| Verdict | **PASS** · `READY_FOR_PRODUCTION_REVIEW = YES` · production **not** deployed |

## Deploy history for this gate

| Order | SHA | Outcome |
|---|---|---|
| 1 | `bfc82cb45cf40453a14208a43fef4660fcc1f067` | **INITIAL DEPLOY SHA** — the exact verified candidate (`origin/develop` at session start). Deployed and healthy with `TLS_MODE=internal`, the only mode that worked. Exposed defects D-1 and D-2. |
| 2 | `fed904f82f0de1fbe3e9b071639b0f7b9f94bd7a` | After `feature/g15c-staging-fix` → `develop`: valid `TLS_MODE` translation, the missing `.env.staging.example`, timezone-independent audit chain. First deployment able to run `TLS_MODE=off` behind the shared proxy. |
| 3 | `9649ec79db189857628ced0b11eaeaf6635fb42c` | **FINAL** — after `feature/g15c-acceptance-tooling` → `develop`: client-runnable restart counts, WAN-tolerant and diagnosable oversize-upload check, browser test for demo labels. Full acceptance run against this SHA. |

Each redeployment was caused by a defect that only real staging exposed. Every fix went
through Git (branch → test → push → merge to `develop` → new SHA → redeploy). **No
application source was edited on the VPS.**

## Image / container identity at the final SHA

| Service | Image | Image ID | Container ID |
|---|---|---|---|
| api | `vip-customs-api:9649ec79db18` | `sha256:69e7916236f3…` | `f870c067a0d2` |
| web | `vip-customs-web:9649ec79db18` | `sha256:bf31eb36f0eb…` | `68ad03f06253` |
| postgres | `postgres:16-alpine` | — | `e9b735928e4e` |
| proxy | `caddy:2-alpine` | — | `6437ce29b465` |

Volumes: `…_pgdata`, `…_uploads`, `…_caddy_data`, `…_caddy_config`. All `RestartCount=0`.

## Networking — shared host, shared reverse proxy

The VPS also runs four unrelated live VIP projects, and ports 80/443 are owned by a **shared**
Caddy (`vip-staging-caddy`, host networking, config `/srv/vip-staging-proxy/Caddyfile`).
Taking it over was forbidden, so this stack sits behind it:

```
internet ──443/80──▶ vip-staging-caddy (shared, real Let's Encrypt for hq.vipgroup.com.vn)
                        └─ reverse_proxy ─▶ 127.0.0.1:18100
                                              └─ vip-customs-ai-staging proxy (TLS_MODE=off)
                                                   ├─ /api/* /health /ready /docs → api:8000
                                                   └─ everything else            → web:80
```

The stack publishes **loopback only** (`127.0.0.1:18100` HTTP, `127.0.0.1:18543` HTTPS);
nothing is exposed to the internet directly. `TLS_MODE=acme` cannot be used on this host
because the ACME HTTP-01 challenge needs ports 80/443, which the shared proxy owns.

Shared Caddyfile changed by backup → append → `caddy validate` → `caddy reload` (zero
downtime, additive). Rollback: `Caddyfile.bak-before-vip-customs-ai-2026-10-09-105445`.

## Redeploying / rolling back

```bash
# deploy an exact SHA (run ON the host; infra/staging/.env must already exist, chmod 600)
cd /opt/vip-customs-ai
DEPLOY_SHA=<40-char-sha> bash scripts/staging/deploy.sh
```

Rollback assets: previous api+web images for all three SHAs are retained on the host, and
`deploy.sh` wrote a pre-deploy `pg_dump -Fc` plus an image manifest to
`/opt/vip-customs-ai/backups/` before each deployment. An independent verified backup with a
recorded SHA256 is in `/opt/backups/vip-customs-ai/`. Procedure: `docs/STAGING_ROLLBACK.md`.

## Host environment file

`infra/staging/.env` is created on the host from `infra/staging/.env.staging.example`
(added in this gate — `deploy.sh` had always referenced it but it did not exist), mode `600`,
git-ignored. `POSTGRES_PASSWORD`, `APP_SECRET_KEY` and `SEED_DEMO_PASSWORD` were generated on
the operator's machine and installed over SSH without ever being printed. Host-specific
values for this deployment: `PUBLIC_HOST=hq.vipgroup.com.vn`,
`PUBLIC_WEB_ORIGIN=https://hq.vipgroup.com.vn`, `TLS_MODE=off`,
`PUBLIC_HTTP_PORT=127.0.0.1:18100`, `PUBLIC_HTTPS_PORT=127.0.0.1:18543`, `AI_PROVIDER=mock`.
See `docs/STAGING_SECRETS.md`. **No secret value appears in Git or in any report.**

---

## Appendix · superseded pre-G15C entries (no deployment happened)

| | |
|---|---|
| PREVIOUS DEVELOP (G14 candidate) | `474f7d84d2c64938ce86ca74fdb33cc0c0c7f2ae` |
| G15 FEATURE HEAD merged | `a95aa83066d48328d9689411092f1bf17f1c2f91` (`feature/g15-staging-acceptance`) |
| MERGE COMMIT | `030933f09304253ddbd96e44998b4b6fc023df20` |
| G15B pinned candidate | `bfc82cb45cf40453a14208a43fef4660fcc1f067` |
| Status then | `BLOCKED_OWNER` (B-03) — no staging host supplied and no `ssh` in the build session, so nothing was deployed and the tooling was only dry-run against the local Docker stack. |
