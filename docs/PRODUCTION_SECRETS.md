# PRODUCTION SECRETS & INPUTS (G18)

Nothing below is stored in Git. Values live in `infra/production/.env` on the production host (chmod 600, owner
`deploy`) or the host's secret manager. `scripts/secret_scan.sh` runs in CI; `tests/test_production_infra.py`
asserts that every secret-bearing key in the template is an empty placeholder.

| Secret / input | Variable | Who provides | Rules |
|---|---|---|---|
| Database password | `POSTGRES_PASSWORD` | generated on host (`secrets.token_urlsafe(36)`) | ≥ 32 chars; DB not published outside the compose network; rotation = change value + `docker compose up -d` (postgres keeps the old password until `ALTER ROLE` — follow the runbook) |
| Application signing key | `APP_SECRET_KEY` | generated on host (`secrets.token_urlsafe(48)`) | ≥ 32 chars; API refuses to start without it outside development; rotation logs every user out |
| AI provider key | `AI_PROVIDER_API_KEY` | **owner** (B-01) | only after the data-processing agreement; vendor console → host env; rotate at the vendor on suspicion; never in logs (redaction policy) |
| AI provider endpoint / model | `AI_PROVIDER_BASE_URL`, `AI_PROVIDER_MODEL` | owner (B-01) | `https://` only in production (self-hosted loopback gateway excepted) |
| OCR provider key (if a separate vendor) | reserved: `DOCUMENT_OCR_PROVIDER` + its own `*_API_KEY` when an OCR adapter is added | owner (B-01) | adapter does not exist yet; do not invent a variable until it does |
| Off-host backup destination credential | rclone config (`~deploy/.config/rclone/rclone.conf`, 0600) or the ssh key for `OFFSITE_TARGET` | **owner** (backup) | write-only/limited bucket policy where the provider supports it; never in `.env` |
| Backup encryption | `OFFSITE_ENCRYPT_RECIPIENT` (public key, not secret) · **private key kept offline by the owner** | owner | the private key is never placed on any server |
| OIDC client credentials (later) | reserved: `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | owner | not implemented; D-012 anticipates replacing the token issuer |
| Deploy SSH keys | `~deploy/.ssh/authorized_keys` | operators | one key per person; revoke individually (`G18_PRODUCTION_ACCESS.md`) |
| TLS | Let's Encrypt account + certs in the `caddy_data` volume | automatic | no secret to manage; back up via VM snapshot |
| Public host / origin | `PUBLIC_HOST`, `PUBLIC_WEB_ORIGIN`, `TLS_MODE` | owner (B-06) | CORS allow-list derives from the origin |
| Runtime mode | `APP_MODE` | owner decision per gate | `limited` until B-01 and B-02 are RESOLVED; `full` refuses to start otherwise |

Controls: `.env*` git-ignored (examples only), `umask 077` in backup scripts, redaction in AI logs, no secret in
`/ready`, `/health` or `/metrics`.
