#!/usr/bin/env bash
# Full local verification: API lint + tests (PostgreSQL) + migrations single head + web typecheck/tests/build + secret scan.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/api"
PY=${PY:-.venv/bin/python}
$PY -m ruff check app tests
$PY -m pytest
heads=$($PY -m alembic heads | wc -l)
[ "$heads" -eq 1 ] || { echo "Expected 1 alembic head, got $heads"; exit 1; }
cd "$ROOT/apps/web"
npx tsc -b
npx vitest run
npx vite build >/dev/null
cd "$ROOT"
bash scripts/secret_scan.sh
echo "VERIFY: ALL CHECKS PASSED"
