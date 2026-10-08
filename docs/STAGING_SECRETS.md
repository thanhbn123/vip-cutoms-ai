# STAGING SECRETS & INPUTS

Nothing below is stored in Git. Fill `infra/staging/.env` on the host (`chmod 600`), or inject via the host's secret manager.

| Variable | Who provides | Rule |
|---|---|---|
| `POSTGRES_PASSWORD` | generated on host | ≥ 32 random chars; rotate on compromise; DB not exposed outside the compose network |
| `APP_SECRET_KEY` | generated on host | ≥ 32 chars; API refuses to start without it when `APP_ENV≠development`; rotation invalidates all tokens |
| `PUBLIC_HOST`, `PUBLIC_WEB_ORIGIN` | owner | hostname + origin; CORS allow-list is derived from it |
| `TLS_MODE` | owner | `internal` (private staging, self-signed), `acme` (public DNS), `off` (upstream TLS) |
| `IMAGE_TAG` | engineering | git SHA of `develop` recorded in `docs/G14_DOCKER_STAGING_PREFLIGHT.md` |
| `SEED_DEMO_PASSWORD` | owner | only for the acceptance demo tenant; ≥ 10 chars; delete the demo users after acceptance |
| provider keys (OCR/LLM) | **not required** | staging boots with `AI_PROVIDER=mock`; real providers are gate G15+ and will use their own variables |

Controls: `scripts/secret_scan.sh` runs in `make verify`/CI; `.env*` is git-ignored (`.env.example` only); logs never print secrets
(verified in G14: the generated `POSTGRES_PASSWORD` does not appear in `docker compose logs`).
