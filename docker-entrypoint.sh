#!/usr/bin/env bash
# LBVD all-in-one entrypoint.
#
#   DATABASE_URL set   -> external database mode (docker-compose, managed MySQL).
#   DATABASE_URL unset -> start an embedded MariaDB inside this container and
#                         seed it from deploy/seed.sql on first start.
#
# Embedded data lives in /var/lib/mysql and does NOT survive a redeploy or a
# container restart on hosts without a persistent volume.
set -euo pipefail

APP_PORT="${PORT:-5000}"
APP_HOST="${HOST:-0.0.0.0}"

if [ -n "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] external database mode"
  exec uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT"
fi

DATADIR="${MYSQL_DATADIR:-/var/lib/mysql}"
SOCKET=/run/mysqld/mysqld.sock

mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld 2>/dev/null || true

if [ ! -d "$DATADIR/mysql" ]; then
  echo "[entrypoint] initialising MariaDB data directory"
  mariadb-install-db --user=mysql --datadir="$DATADIR" \
    --auth-root-authentication-method=normal >/dev/null
fi

echo "[entrypoint] starting MariaDB"
mariadbd --user=mysql --datadir="$DATADIR" --socket="$SOCKET" \
  --bind-address=127.0.0.1 --port=3306 \
  --innodb-buffer-pool-size=64M --key-buffer-size=8M \
  --performance-schema=OFF --skip-log-bin &
MARIADB_PID=$!

ready=0
for _ in $(seq 1 60); do
  if mariadb-admin --socket="$SOCKET" -uroot ping >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$MARIADB_PID" 2>/dev/null; then
    echo "[entrypoint] MariaDB exited during startup" >&2
    exit 1
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "[entrypoint] MariaDB did not become ready within 60s" >&2
  exit 1
fi

mariadb --socket="$SOCKET" -uroot -e \
  "CREATE DATABASE IF NOT EXISTS \`lbvd\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

if mariadb --socket="$SOCKET" -uroot -N -e \
  "SELECT 1 FROM information_schema.tables WHERE table_schema='lbvd' AND table_name='personcv'" \
  | grep -q 1; then
  echo "[entrypoint] existing data found, skipping seed"
else
  echo "[entrypoint] seeding database from deploy/seed.sql"
  mariadb --socket="$SOCKET" -uroot lbvd < /app/deploy/seed.sql
fi

export DATABASE_URL="mysql+pymysql://root@localhost/lbvd?unix_socket=${SOCKET}&charset=utf8mb4"
echo "[entrypoint] starting application on ${APP_HOST}:${APP_PORT}"
exec uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT"
