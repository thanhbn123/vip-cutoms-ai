# G18 — MONITORING AND ALERTING

Status: **requirements defined; free local metrics implemented (`/metrics`); the notification destination and
the monitoring host are OWNER INPUTS.** No paid service required.

## 1. What the application exposes (implemented)

| Endpoint | Content |
|---|---|
| `GET /health` | liveness: `status`, `mode`, `release_sha` |
| `GET /ready` | readiness (200/503): `mode`, `checks.database`, `checks.migrations` vs `migration_head` + `migration_in_sync`, `checks.providers.<cap>` (configured/healthy/is_mock), `checks.customs_data_authoritative.<kind>` + `all_authoritative`, `checks.backup_status`, `release_sha`, `blocking[]` |
| `GET /metrics` | Prometheus text: `vip_http_requests_total{method,status_class}`, `vip_http_5xx_total`, `vip_app_mode_info{mode}`, `vip_ai_calls_total`, `vip_ai_failures_total`, `vip_ai_cost_usd_today`, `vip_ai_tokens_today{direction}`, `vip_ai_provider_configured{capability,provider}`, `vip_customs_dataset_age_days{kind,authoritative}`, `vip_backup_age_hours` |

No label carries tenant, user, case or document identifiers; no secret appears. `/metrics` is unauthenticated
like `/health`; restrict it at the proxy to the monitoring host's IP in production (Caddyfile `remote_ip`
matcher — follow-up when B-06 is decided).

## 2. Requirements → signal → threshold (PROPOSED)

| Requirement | Signal | Alert when |
|---|---|---|
| `/health` | HTTP probe every 60 s | non-200 for 2 consecutive probes |
| `/ready` | HTTP probe every 60 s | 503 for 3 consecutive probes (full mode: any 503 is actionable; `blocking[]` says why) |
| container restarts | `docker inspect … RestartCount` via node exporter/cron, or `docker events` | any restart of `api`/`postgres`/`proxy` in 10 min |
| disk usage | node metrics / `df` cron | > 80 % on `/`, backup volume, Docker root |
| memory | node metrics / `docker stats` | container near its limit (api 1 g, postgres 1 g) for 5 min |
| DB connectivity | `/ready` `checks.database` | `error:*` |
| backup freshness | `vip_backup_age_hours` + systemd unit result | > 26 h, or `vip-customs-backup*.service` failed |
| TLS expiry | external cert check (e.g. the monitor's TLS probe) | < 14 days to expiry |
| 5xx rate | `rate(vip_http_5xx_total[5m]) / rate(vip_http_requests_total[5m])` | > 1 % for 10 min, or any 5xx burst > 10/min |
| reviewer backlog | `GET /api/v1/dashboard/summary` (authenticated) or a DB query on open CRITICAL issues/REVIEW_REQUIRED cases | cases in `REVIEW_REQUIRED`/`BLOCKED` older than 2 business days (owner threshold) |
| provider failures | `increase(vip_ai_failures_total[15m])`, `/ready` `providers.*.healthy` | > 5 failures / 15 min, or unhealthy for 5 min |
| provider costs | `vip_ai_cost_usd_today` vs `AI_DAILY_BUDGET_USD` | > 80 % of budget; budget reached (calls refused) |
| authoritative dataset age | `vip_customs_dataset_age_days{authoritative="true"}` | older than the source's cadence (e.g. > 45 days for monthly sources) or no authoritative series present in full mode |
| migration drift | `/ready` `migration_in_sync=false` | immediately |

## 3. Reference stack (free, single host or the owner's monitor host)

- **Uptime Kuma** (or any HTTP monitor): `/health`, `/ready`, TLS expiry, keyword check on `/metrics`
  (`vip_app_mode_info{mode="limited"} 1` to catch an unintended mode change).
- **Prometheus + node_exporter + Alertmanager** (or Grafana Agent) scraping `/metrics` and host metrics; alert
  rules from §2. Alertmanager routes to the owner's destination (e-mail/Telegram/Slack webhook — owner input).
- **systemd** `OnFailure=` on the backup units → a small notify script, or journald → the monitor.
- Logs: Docker json-file rotation is already in the production overlay; forward with `promtail`/`vector` if a
  log store is wanted later.

## 4. Runbook hooks

Each alert links to `docs/PRODUCTION_RUNBOOK.md` §5/§6 and, for backups, `G18_OFFHOST_BACKUP.md` §4. Provider
alerts: `G18_AI_PROVIDER_SECURITY.md` §4.
