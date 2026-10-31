#!/bin/sh
# Run FastAPI against the externally configured MySQL/MariaDB database.
set -eu

# Render supplies PORT; keep 5000 as the default for local Docker Compose.
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-5000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
