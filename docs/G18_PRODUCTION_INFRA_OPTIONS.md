# G18 — PRODUCTION INFRASTRUCTURE OPTIONS (B-06 decision package)

**Nothing here is decided or configured.** No DNS, host or domain has been touched. The owner chooses; this
gate prepares the comparison and a recommendation. Current state: staging on a shared VPS
(`160.22.170.20`, `hq.vipgroup.com.vn`) behind a **shared** Caddy that also fronts unrelated projects.

## 1. Options

| Criterion | **A — same VPS as staging** | **B — dedicated production VPS (recommended)** | **C — managed container platform** |
|---|---|---|---|
| Isolation | none: shares kernel, disk, proxy and reboot schedule with staging + unrelated services; a staging mistake can take production down | full host isolation; staging stays a test bed | strong (platform-managed), but shared control plane |
| Cost (indicative) | +0 host; hidden cost = risk | one more VPS of the staging class (4 vCPU / 8 GB / 80 GB SSD is ample for the current stack) | platform fee + managed PostgreSQL; typically 2–4× option B |
| Backup | same disk as staging; off-host copy mandatory | local nightly + off-host (G18 scripts) ; snapshot of the whole VM available from most providers | managed DB backups (point-in-time) + object storage for uploads; off-host already by nature |
| Rollback | redeploy previous SHA (compose) | redeploy previous SHA; VM snapshot for host-level rollback | platform rollout history |
| Blast radius | highest: staging, production and other tenants' sites | one product | one product; platform incidents affect many customers |
| TLS | must stay behind the shared Caddy (`TLS_MODE=off`), certificate lifecycle outside this repo | the stack's own Caddy owns 80/443 with `TLS_MODE=acme` (already tested path) — or a dedicated host proxy | platform-terminated TLS |
| Monitoring | shared host metrics muddled by other services | clean per-host metrics; `/metrics` + `/ready` scraped by a free monitor | platform metrics + `/metrics` |
| Maintenance | OS updates/reboots negotiated with other services' owners | owned entirely by this product's operator | platform handles OS; app-level unchanged |
| Security | shared Docker daemon = root-equivalent neighbours; demo users and real data on one host | deploy user + Docker group only on this host; firewall only 80/443/22 | platform IAM; secrets manager; needs review of data residency |
| Compose compatibility | works (current) | works unchanged (`infra/production/docker-compose.production.yml` overlay) | needs conversion (Kubernetes/ECS manifests) — not prepared in this repo |

## 2. Recommendation

**Option B: a dedicated production VPS, separate from staging**, same provider/region family as staging for
operational familiarity, provisioned by the owner. Rationale: the stack is small, compose-native and already
hardened for a single host (log rotation, memory limits, healthchecks, backup scripts, deploy user model);
option B removes the shared-proxy and shared-host risks that are the whole of B-06 without the migration cost
of option C. Option A is **not recommended** and should be chosen only with an explicit written acceptance of
the shared blast radius. Option C becomes attractive only if the owner wants managed PostgreSQL with
point-in-time recovery more than they want operational simplicity.

Suggested production domain (documentation only, **not configured**): `customs.vipgroup.com.vn` (staging keeps
`hq.vipgroup.com.vn`). DNS, certificate issuance and the proxy model are configured only after the owner's
decision (`G18_OWNER_INPUTS.md` → B-06).

## 3. Production proxy design (decision inside B-06)

| Aspect | Shared host proxy (as staging today) | **Dedicated proxy = the stack's own Caddy (recommended with option B)** |
|---|---|---|
| TLS termination | shared Caddy terminates; stack runs `TLS_MODE=off` on loopback ports | stack's `proxy` service terminates with `TLS_MODE=acme`; Let's Encrypt via HTTP-01 |
| Port ownership | 80/443 owned by the shared proxy; stack on `127.0.0.1:18xxx` | 80/443 owned by this compose project only |
| Reload safety | a bad shared config affects every site; reloads outside this repo | `docker compose up -d` recreates only this proxy; Caddyfile is versioned here and tested (`tests/test_staging_infra.py`) |
| Certificate management | shared Caddy's storage, not backed up by this repo | `caddy_data` volume (ACME account + certs) — include in host snapshot; re-issuance is automatic if lost |
| Proxy backup | n/a (outside scope) | Caddyfile in Git; `caddy_data` volume in VM snapshot |
| Rollback | coordinate with other sites | redeploy previous SHA; Caddyfile is part of the SHA |
| Health routing | shared proxy forwards blindly | `/health` `/ready` proxied to `api`; `web` healthcheck in the production overlay; Caddy only routes to healthy upstreams when `health_uri` is configured (follow-up: add `health_uri /health` to the reverse_proxy block when B-06 is decided) |
| WebSocket/SSE | not used by the product today | Caddy supports both by default if ever needed |
| Security headers | set by the stack's Caddyfile (HSTS, CSP, nosniff, X-Frame-Options, Referrer-Policy) and would be lost if a shared proxy bypassed it | always applied |
| Rate limiting on `/auth/login` | none | add at the proxy (Caddy rate-limit module or fail2ban on access logs) before internet-facing full mode |

Firewall for option B: inbound 22 (deploy key only, see `G18_PRODUCTION_ACCESS.md`), 80, 443; everything
else closed; PostgreSQL and the API never published outside the compose network (already true).

## 4. What is already prepared for option B

- `infra/production/docker-compose.production.yml` (overlay: log rotation, memory limits, `web` healthcheck,
  `restart: always`, read-only backup-status mount), `.env.production.example` (G18 keys, safe defaults).
- `scripts/production/backup.sh` + `backup_offsite.sh`, systemd units for both.
- `/ready` full-mode gates, `/metrics`, `APP_MODE=limited` default for the first production deployment.
- `docs/PRODUCTION_RUNBOOK.md`, `G18_PRODUCTION_ACCESS.md`, `PRODUCTION_SECRETS.md`, `G18_MONITORING_ALERTS.md`.

## 5. Not done in this gate (by rule)

No host ordered, no DNS record, no certificate, no deployment. B-06 remains an **OWNER DECISION**.
