#!/usr/bin/env bash
# Demo-only launcher for Deepnote.
#
# Runs MariaDB and the FastAPI app on port 8080, which is the only port
# Deepnote exposes (via "Incoming connections").
#
# Deepnote persists ~/work across machine restarts, so the database directory
# and the virtualenv live there. Everything outside ~/work (apt packages,
# /var/lib/mysql) is lost when the machine stops.
#
# Start it from the Deepnote terminal:
#   bash deploy/deepnote/start.sh
#
# Or auto-start it from the project's "Init" notebook:
#   import os, subprocess
#   repo = os.path.expanduser("~/work/lbvd")
#   subprocess.Popen(["bash", os.path.join(repo, "deploy/deepnote/start.sh")],
#                    cwd=repo, start_new_session=True)
#
# This is NOT a production deployment. See DEEPNOTE.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

WORK="${HOME}/work"
mkdir -p "$WORK"

# ---------------------------------------------------------------- MariaDB
have_mariadb() {
  command -v mariadbd >/dev/null 2>&1 || [ -x /usr/sbin/mariadbd ]
}
if ! have_mariadb; then
  echo "[deepnote] installing mariadb-server (gone after a machine restart)"
  $SUDO apt-get update -qq
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq mariadb-server
fi
MARIADBD="$(command -v mariadbd 2>/dev/null || echo /usr/sbin/mariadbd)"

# ---------------------------------------------------------------- Python
VENV="${LBVD_VENV:-$WORK/.lbvd-venv}"
if [ ! -x "$VENV/bin/python" ]; then
  echo "[deepnote] creating virtualenv in $VENV"
  python -m venv "$VENV" || {
    $SUDO apt-get install -y -qq python3-venv
    python -m venv "$VENV"
  }
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r requirements.txt slowapi uvicorn pyjwt openpyxl

# ------------------------------------------------------- persistent database
DATADIR="${LBVD_MYSQL_DATA:-$WORK/.lbvd-mysql}"
SOCK="$DATADIR/mysqld.sock"
PIDFILE="$DATADIR/mysqld.pid"
DBPORT="${LBVD_MYSQL_PORT:-3307}"
mkdir -p "$DATADIR"

INSTALL_DB="$(command -v mariadb-install-db || command -v mysql_install_db)"
if [ ! -d "$DATADIR/mysql" ]; then
  echo "[deepnote] initialising MariaDB in $DATADIR"
  "$INSTALL_DB" --no-defaults --datadir="$DATADIR" \
    --auth-root-authentication-method=normal >/dev/null
fi

if ! mariadb-admin --no-defaults --socket="$SOCK" -uroot ping >/dev/null 2>&1; then
  echo "[deepnote] starting MariaDB on port $DBPORT"
  rm -f "$SOCK" "$PIDFILE"   # stale socket left behind by a stopped machine
  RUN_AS=""
  [ "$(id -u)" -eq 0 ] && RUN_AS="--user=root"
  "$MARIADBD" --no-defaults $RUN_AS \
    --datadir="$DATADIR" --socket="$SOCK" --pid-file="$PIDFILE" \
    --bind-address=127.0.0.1 --port="$DBPORT" \
    --innodb-buffer-pool-size=64M --key-buffer-size=8M \
    --performance-schema=OFF --skip-log-bin \
    >"$DATADIR/mysqld.log" 2>&1 &
fi

ready=0
for _ in $(seq 1 60); do
  if mariadb-admin --no-defaults --socket="$SOCK" -uroot ping >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "[deepnote] MariaDB did not start; see $DATADIR/mysqld.log" >&2
  exit 1
fi

mariadb --no-defaults --socket="$SOCK" -uroot -e \
  "CREATE DATABASE IF NOT EXISTS lbvd CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

if mariadb --no-defaults --socket="$SOCK" -uroot -N -e \
  "SELECT 1 FROM information_schema.tables WHERE table_schema='lbvd' AND table_name='personcv'" \
  | grep -q 1; then
  echo "[deepnote] existing data found, skipping seed"
else
  echo "[deepnote] importing deploy/seed.sql"
  mariadb --no-defaults --socket="$SOCK" -uroot lbvd < deploy/seed.sql
fi

# ------------------------------------------------------------------- app
# Set these in Deepnote (Environment -> Environment variables) so sessions
# survive restarts; otherwise a new random secret is generated each boot.
export DATABASE_URL="mysql+pymysql://root@localhost/lbvd?unix_socket=${SOCK}&charset=utf8mb4"
export DEBUG="${DEBUG:-false}"
export COOKIE_HTTPS_ONLY="${COOKIE_HTTPS_ONLY:-false}"
export SESSION_SECRET="${SESSION_SECRET:-$("$VENV/bin/python" -c 'import secrets; print(secrets.token_hex(32))')}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-$("$VENV/bin/python" -c 'import secrets; print(secrets.token_hex(32))')}"

echo "[deepnote] starting app on 0.0.0.0:${PORT:-8080}"
exec "$VENV/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
