#!/usr/bin/env bash
# Create local dev + test databases on a native PostgreSQL 16 (when Docker is unavailable).
set -euo pipefail
psql_admin() { sudo -u postgres psql -v ON_ERROR_STOP=1 "$@" 2>/dev/null || su postgres -c "psql -v ON_ERROR_STOP=1 $*"; }
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='vip_customs'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE ROLE vip_customs LOGIN PASSWORD 'vip_customs' CREATEDB;"
for db in vip_customs vip_customs_test; do
  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 || sudo -u postgres createdb -O vip_customs "$db"
done
echo "dev databases ready (local-only credentials vip_customs/vip_customs)"
