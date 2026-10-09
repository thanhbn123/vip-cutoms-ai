#!/usr/bin/env bash
# Full local verification: API lint + tests (PostgreSQL) + migrations single head + web typecheck/tests/build + secret scan.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY=${PY:-$ROOT/apps/api/.venv/bin/python}
cd "$ROOT/apps/api"
$PY -m ruff check app tests
$PY -m pytest
# Infrastructure tests (infra/staging contracts) — no database, so kept out of the app suite.
(cd "$ROOT" && $PY -m pytest tests -q)
heads=$($PY -m alembic heads | wc -l)
[ "$heads" -eq 1 ] || { echo "Expected 1 alembic head, got $heads"; exit 1; }
cd "$ROOT/apps/web"
npx tsc -b
npx vitest run
npx vite build >/dev/null
cd "$ROOT"
bash scripts/secret_scan.sh
echo "VERIFY: ALL CHECKS PASSED"
