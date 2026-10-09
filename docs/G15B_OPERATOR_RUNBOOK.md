# G15B OPERATOR RUNBOOK — real staging deployment of `bfc82cb45cf40453a14208a43fef4660fcc1f067`

Run from any machine that can `ssh root@160.22.170.20` (the Claude build container cannot: port 22 is blocked by its egress policy and
no SSH credential is available to it). Every step below maps to a section of the G15B brief and to committed scripts; paste the outputs into
`docs/G15_STAGING_ACCEPTANCE_REPORT.md` (section "G15B evidence").

## 0. Facts already verified (2026-10-09)
- `origin/main` = `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0`, `origin/develop` = `bfc82cb45cf40453a14208a43fef4660fcc1f067` (DEPLOY_SHA).
- DNS: `hq.vipgroup.com.vn` → `160.22.170.20` (DNS_PENDING = NO).
- Images for this SHA build and pass the full acceptance dry-run in Docker (`docs/G15_STAGING_ACCEPTANCE_REPORT.md`).

## 2–4. Identity, inventory, DNS, proxy (read-only)
```bash
ssh root@160.22.170.20 'hostname; whoami; uname -a; cat /etc/os-release | head -3; df -h /; free -h; docker version --format "{{.Server.Version}}"; docker compose version --short'
ssh root@160.22.170.20 'docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"; ss -lntp; ls -la /opt'
ssh root@160.22.170.20 'ps aux | egrep "caddy|nginx|traefik|cloudflared" | grep -v grep || echo "no existing reverse proxy"; ss -lntp | egrep ":80 |:443 " || echo "80/443 free"'
```
STOP if the host is not the intended staging machine. If 80/443 are already used by another proxy: back up its config, add a vhost for
`hq.vipgroup.com.vn` → `api:8000` (`/api/*`, `/health`, `/ready`, `/docs`) and `web:80` (rest), and set `TLS_MODE=off` + remove the `proxy`
service from the compose command (`--scale proxy=0`) so VIP Customs does not fight for the ports.

## 5–6. Backup dir, checkout exact SHA
```bash
ssh root@160.22.170.20 'mkdir -p /opt/backups/vip-customs-ai; [ -d /opt/vip-customs-ai/.git ] && (cd /opt/vip-customs-ai && git rev-parse HEAD && docker compose -p vip-customs-ai-staging ps) || echo FIRST_DEPLOY=YES'
ssh root@160.22.170.20 '[ -d /opt/vip-customs-ai/.git ] || git clone https://github.com/thanhbn123/vip-cutoms-ai.git /opt/vip-customs-ai; cd /opt/vip-customs-ai && git fetch origin --prune && git checkout --detach bfc82cb45cf40453a14208a43fef4660fcc1f067 && git rev-parse HEAD && git status --short'
```
HEAD must print `bfc82cb45cf40453a14208a43fef4660fcc1f067` and `git status --short` must be empty.

## 7–8. Staging env (secrets generated on the server, never committed, never printed)
```bash
ssh root@160.22.170.20 'cd /opt/vip-customs-ai && cp -n infra/staging/.env.staging.example infra/staging/.env && \
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")|; \
          s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")|; \
          s|^PUBLIC_HOST=.*|PUBLIC_HOST=hq.vipgroup.com.vn|; s|^PUBLIC_WEB_ORIGIN=.*|PUBLIC_WEB_ORIGIN=https://hq.vipgroup.com.vn|; \
          s|^TLS_MODE=.*|TLS_MODE=acme|; s|^IMAGE_TAG=.*|IMAGE_TAG=bfc82cb45cf4|; s|^SEED_DEMO_PASSWORD=.*|SEED_DEMO_PASSWORD=$(python3 -c "import secrets;print(secrets.token_urlsafe(12))")|" infra/staging/.env && \
  chmod 600 infra/staging/.env && sed -E "s/^(POSTGRES_PASSWORD|APP_SECRET_KEY|SEED_DEMO_PASSWORD)=.*/\1=<redacted>/" infra/staging/.env'
```
`APP_ENV=staging`, `AI_PROVIDER=mock` stay as in the example (parser / HS / Copilot = mock; knowledge = DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING).

## 9–12. Build, start, migrate, internal health (one script)
```bash
ssh root@160.22.170.20 'cd /opt/vip-customs-ai && DEPLOY_SHA=bfc82cb45cf40453a14208a43fef4660fcc1f067 DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deploy.sh'
```
Prints: host identity, inventory, HEAD check, FIRST_DEPLOY, image IDs/digests, `docker compose ps`, `alembic current` (`0010_copilot_meta (head)`),
`heads=1`, in-container `/health` and `/ready`. The `migrate` service applies migrations before `api` starts.

## 13. Domain / TLS
Caddy (`infra/staging/Caddyfile`) obtains a Let's Encrypt certificate automatically with `TLS_MODE=acme` once 80/443 reach the container.
```bash
curl -I https://hq.vipgroup.com.vn/            # 200, valid chain, HSTS header
curl -fsS https://hq.vipgroup.com.vn/health && curl -fsS https://hq.vipgroup.com.vn/ready
curl -sI http://hq.vipgroup.com.vn/ | head -3   # 308 → https
```
If Cloudflare proxies the domain, record it and additionally test the origin with `curl --resolve hq.vipgroup.com.vn:443:160.22.170.20`.

## 14–24. Seed, acceptance A–P, Playwright, negative tests, labels, performance, restart, down/up, backup, restore, logs (one script)
From a workstation with Node 22 + Python venv of this repo (or on the host itself):
```bash
export BASE_URL=https://hq.vipgroup.com.vn WEB_URL=https://hq.vipgroup.com.vn
export SEED_DEMO_PASSWORD='<value from infra/staging/.env on the host>'
export COMPOSE="ssh root@160.22.170.20 docker compose -p vip-customs-ai-staging -f /opt/vip-customs-ai/infra/staging/docker-compose.staging.yml --env-file /opt/vip-customs-ai/infra/staging/.env"
bash scripts/staging/acceptance.sh        # writes artifacts/test-results/staging-acceptance.txt
```
(`COMPOSE` may be an `ssh … docker compose …` prefix: the script word-splits it and never evals.) Expected: Playwright `1 passed`; `ACCEPTANCE_HTTP: 17/17`;
`NEGATIVE_TESTS: 18/18`; restart + down/up with unchanged counts and restart counts 0; backup size > 0 and `RESTORE_TEST cases=… audit=…`;
`secret-pattern hits: 0`. Copy the backup to `/opt/backups/vip-customs-ai/` with its `sha256sum`.

## 22. Rollback drill (structural, FIRST_DEPLOY)
`docs/STAGING_ROLLBACK.md`: previous image refs are recorded by deploy.sh (`backups/previous-images-*.txt`, empty on first deploy); DB dump exists
from step 20; rollback = `docker compose … down` (no `-v`) → set `IMAGE_TAG` to the previous SHA → `up -d` (or `pg_restore` the dump).

## 25. Owner-visible UI check
Log in at https://hq.vipgroup.com.vn as `reviewer@demo.local`; confirm the 9 V12 pages, the yellow banner "DEMO DATA — NON-AUTHORITATIVE — NOT
FOR CUSTOMS FILING", Goods `CT-88 8537 BLOCKED`, release gate BLOCKED, and the draft's `legal_notice`.

## 26. If anything fails
Do not edit the server tree. Fix on `feature/g15b-staging-fix` → tests → merge to `develop` → new SHA → re-run from step 6 with that SHA.
