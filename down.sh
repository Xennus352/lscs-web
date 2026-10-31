#!/usr/bin/env bash
# Stop the LBVD FastAPI app (started manually with run.sh / uvicorn,
# or as the lbvd-app / lbvd-caddy containers via docker compose)
# and the lbvd-mysql database container if it is running.
set -euo pipefail
cd "$(dirname "$0")"

# ---- Stop the uvicorn app (local run.sh / docker entrypoint) ---------------
# Find the uvicorn process serving app.main:app (match the full command line).
PID=$(pgrep -f "uvicorn app.main:app" || true)

if [ -n "$PID" ]; then
  echo "Stopping LBVD app (PID $PID)..."
  kill "$PID" 2>/dev/null || true

  # Wait up to 10 seconds for it to exit.
  for i in $(seq 1 10); do
    if ! kill -0 "$PID" 2>/dev/null; then
      echo "App stopped."
      break
    fi
    sleep 1
  done

  # Force-kill if still alive.
  if kill -0 "$PID" 2>/dev/null; then
    echo "App still running, force-killing..."
    kill -9 "$PID" 2>/dev/null || true
    echo "App force-killed."
  fi
else
  echo "No LBVD app (uvicorn app.main:app) process found."
fi

# ---- Stop the FastAPI app container (docker compose) -----------------------
if command -v docker >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' | grep -qx "lbvd-app"; then
    echo "Stopping lbvd-app container..."
    docker stop lbvd-app >/dev/null 2>&1 || true
    echo "lbvd-app container stopped."
  else
    echo "lbvd-app container is not running."
  fi

  # Also stop Caddy if it is part of the prod stack.
  if docker ps --format '{{.Names}}' | grep -qx "lbvd-caddy"; then
    echo "Stopping lbvd-caddy container..."
    docker stop lbvd-caddy >/dev/null 2>&1 || true
    echo "lbvd-caddy container stopped."
  fi
else
  echo "Docker not available, skipping container shutdown."
fi

# ---- Stop the database container -------------------------------------------
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx "lbvd-mysql"; then
  echo "Stopping lbvd-mysql container..."
  docker stop lbvd-mysql >/dev/null 2>&1 || true
  echo "Database container stopped."
else
  echo "lbvd-mysql container is not running (or docker unavailable)."
fi

echo "Done."
