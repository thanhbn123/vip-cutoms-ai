# VIP Customs AI — local task runner (native PostgreSQL by default; see docs/LOCAL_DEVELOPMENT.md)
SHELL := /bin/bash
API := apps/api
WEB := apps/web
PY  := $(API)/.venv/bin/python
export DATABASE_URL ?= postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs

.PHONY: help setup db dev dev-api dev-web test test-api test-web lint typecheck build db-migrate db-downgrade db-reset-test seed e2e verify docker-up docker-down docker-smoke docker-acceptance clean

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

setup: ## create venv + install api/dev deps + npm ci
	cd $(API) && python3.12 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'
	cd $(WEB) && npm ci --no-audit --no-fund

db: ## create local role + dev/test databases (native PostgreSQL 16)
	bash scripts/dev_db.sh

db-migrate: ## alembic upgrade head (dev DB)
	cd $(API) && .venv/bin/alembic upgrade head

db-downgrade: ## alembic downgrade one step (dev DB)
	cd $(API) && .venv/bin/alembic downgrade -1

db-reset-test: ## drop + recreate schema of the test DB and migrate from zero
	cd $(API) && DATABASE_URL=postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs_test \
	  .venv/bin/python -c "from sqlalchemy import create_engine,text;e=create_engine('postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs_test');c=e.connect();c.execute(text('DROP SCHEMA public CASCADE; CREATE SCHEMA public;'));c.commit()" \
	  && DATABASE_URL=postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs_test .venv/bin/alembic upgrade head

seed: ## seed demo tenant/users/datasets + V12 reference case (needs SEED_DEMO_PASSWORD)
	cd $(API) && .venv/bin/python scripts/seed_demo.py --with-case

dev-api: ## run API with reload on :8000
	cd $(API) && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-web: ## run Vite dev server on :5173 (proxies /api → :8000)
	cd $(WEB) && npx vite

dev: ## run API + web together (Ctrl+C stops both)
	@trap 'kill 0' INT TERM; $(MAKE) dev-api & $(MAKE) dev-web & wait

test-api: ## backend unit + integration tests (PostgreSQL test DB)
	cd $(API) && .venv/bin/pytest

test-web: ## frontend unit tests
	cd $(WEB) && npx vitest run

test: test-api test-web ## all unit/integration tests

lint: ## ruff (api) 
	cd $(API) && .venv/bin/ruff check app tests scripts

typecheck: ## tsc (web)
	cd $(WEB) && npx tsc -b

build: ## production web build
	cd $(WEB) && npx vite build

e2e: ## browser E2E on the real stack (test DB reset → seed → api → web → playwright). PW_CHROMIUM_PATH optional.
	bash scripts/e2e.sh

verify: ## everything CI runs + secret scan
	bash scripts/verify.sh

docker-up: ## docker compose stack (needs .env with POSTGRES_PASSWORD, APP_SECRET_KEY)
	docker compose -f infra/docker-compose.yml --env-file .env up --build

docker-down:
	docker compose -f infra/docker-compose.yml --env-file .env down -v

docker-smoke: ## clean compose boot from zero + host-side health/ready/migration checks → artifacts/test-results/docker-smoke.txt
	bash scripts/docker_smoke.sh

docker-acceptance: ## seed inside container → Playwright → owner flow A–P over HTTP against the compose stack (SEED_DEMO_PASSWORD optional)
	bash scripts/docker_acceptance.sh

clean:
	rm -rf $(WEB)/dist $(WEB)/test-results $(API)/.pytest_cache local-data
