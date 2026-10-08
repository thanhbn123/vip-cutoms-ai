#!/usr/bin/env bash
# Lightweight secret scan over tracked files (no network). Fails on likely credentials.
set -euo pipefail
cd "$(dirname "$0")/.."
pattern='(sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]{10,})'
if git ls-files -z | xargs -0 grep -nIE "$pattern" -- 2>/dev/null; then
  echo "SECRET SCAN: possible secret found"; exit 1
fi
if git ls-files | grep -E '(^|/)\.env$'; then echo "SECRET SCAN: .env is tracked"; exit 1; fi
echo "SECRET SCAN: clean"
