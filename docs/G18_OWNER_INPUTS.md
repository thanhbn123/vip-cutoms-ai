# G18 — OWNER INPUTS REQUIRED (exact list)

Everything the engineering side could prepare without these inputs is done (`docs/G18A_REPORT.md`). Each item
below names exactly what must be provided, where it goes, and what it unblocks. Until an item is provided the
corresponding blocker stays `BLOCKED_OWNER`.

## B-01 — Real AI / OCR provider

| # | Input | Format | Goes to |
|---|---|---|---|
| 1 | Selected LLM vendor and model for extraction / HS reasoning / Copilot | vendor name, model id, region | `G18_OWNER_INPUTS.md` record + `AI_PROVIDER_MODEL` |
| 2 | Endpoint base URL (chat-completions compatible) | `https://…/v1` | `AI_PROVIDER_BASE_URL` (host env only) |
| 3 | API credential | vendor key | `AI_PROVIDER_API_KEY` on the **staging** host first (chmod 600); never in Git/chat |
| 4 | Billing/account readiness | account active, payment method, spend limit at the vendor | vendor console; `AI_DAILY_BUDGET_USD` + price per 1k tokens in env |
| 5 | Data-processing agreement covering customer trade documents (retention, training opt-out, region) | signed document / vendor terms reference | legal archive; referenced in `G18_AI_PROVIDER_SECURITY.md` §2 |
| 6 | OCR decision: same vendor (vision model) or a separate OCR vendor, or "scanned documents stay manual for now" | one of the three | if a vendor: an OCR adapter is a code change behind `DocumentOcrProvider` |
| 7 | 20-document acceptance sample with reviewer truth (real, anonymised if needed) | files + expected field values | staging acceptance (`G18_AI_PROVIDER_REQUIREMENTS.md` §5) |
| 8 | Accuracy threshold for acceptance | e.g. "≥ 0.90 precision on critical fields" | acceptance record |

## B-02 — Authoritative customs data

| # | Input | Format | Goes to |
|---|---|---|---|
| 1 | Authoritative source per domain (HS/tariff, VAT, FTA rates + C/O rules, specialized management) | publisher name + product/feed name | `G18_LEGAL_SOURCE_GOVERNANCE.md` §1 record |
| 2 | Licence / access method | contract or subscription reference; credentials for the licensed channel (kept off-Git) | steward archive |
| 3 | Delivery format and schema | sample file(s) | adapter design (`CustomsDataProvider`) |
| 4 | Update cadence and notification channel | e.g. "monthly + ad-hoc amendments, e-mail list X" | `G18_DATA_UPDATE_PROCESS.md` §1, dataset-age alert threshold |
| 5 | Named data steward (ADMIN) and named verifier (ADMIN/SENIOR_REVIEWER) | two people | user accounts + process |
| 6 | HS key depth used in filings (8-digit national lines expected) | number | evaluator lookup extension (longest-prefix match) |
| 7 | Spot-check policy (N records, which codes) | numbers | `G18_DATA_UPDATE_PROCESS.md` §3 |

## B-06 — Production infrastructure

| # | Input | Format | Goes to |
|---|---|---|---|
| 1 | Hosting option: **B (dedicated VPS, recommended)**, A (shared staging host), or C (managed platform) | letter | `G18_PRODUCTION_INFRA_OPTIONS.md` decision record |
| 2 | Production host (if A/B): provider, region, size, IP | details | provisioning; `PUBLIC_*` env |
| 3 | Production domain | FQDN (suggested `customs.vipgroup.com.vn`) | `PUBLIC_HOST`, `PUBLIC_WEB_ORIGIN`; DNS by owner |
| 4 | TLS / proxy model: dedicated stack Caddy (`TLS_MODE=acme`, recommended) or shared host proxy (`TLS_MODE=off`) | one | `TLS_MODE`, port bindings |
| 5 | Administrator account for one-time root tasks (systemd units, OS updates) | named person + key | host |
| 6 | Deploy operators' SSH public keys | keys | `~deploy/.ssh/authorized_keys` |

## Backup

| # | Input | Format | Goes to |
|---|---|---|---|
| 1 | Off-host destination: rclone remote (object storage, different provider/region) **or** ssh host | `remote:bucket/prefix` or `user@host:/path` | `OFFSITE_METHOD`, `OFFSITE_TARGET` |
| 2 | Destination credential | provider key with limited (write/list) policy, or ssh key | deploy user's rclone config / ssh key — never `.env` |
| 3 | Encryption key pair (age) — public key to the server, private key offline | `age1…` public key | `OFFSITE_ENCRYPT_RECIPIENT` |
| 4 | Approval of retention 7 daily / 4 weekly / 6 monthly (or alternative numbers) | yes / numbers | `OFFSITE_RETENTION_*` |
| 5 | Monthly restore-drill owner | named person | runbook log |

## Monitoring

| # | Input | Format | Goes to |
|---|---|---|---|
| 1 | Notification destination (e-mail list, Telegram/Slack webhook, SMS) | address/webhook | Alertmanager / Uptime Kuma notification |
| 2 | Monitoring host: on the production VPS (minimal) or a separate box / existing monitor | choice | monitor install |
| 3 | On-call / response expectation (business hours vs 24×7) | text | alert severities |
| 4 | Reviewer-backlog threshold (days) | number | backlog alert |

## B-07 — Demo users (execution)

| # | Input | Goes to |
|---|---|---|
| 1 | Confirmation that staging acceptance is signed off and the demo accounts may be deactivated | run `scripts/staging/deactivate_demo_users.sh --execute` on the staging host (`docs/G18_B07_DEMO_USERS.md`) |
| 2 | A real (non-demo) ADMIN account for the DEMO tenant if that tenant will keep being used | create via `POST /users` before deactivation; the script's `--verify` checks it |

## Not requested (and must not be supplied)

- No VNACCS/ECUS credentials or endpoints: no submission adapter exists and none is authorised.
- No "temporary" real tariff data pasted into the demo fixtures: authoritative data enters only via the import
  + verification workflow.
