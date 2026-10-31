#!/usr/bin/env bash
# Start the LBVD FastAPI website. Requires lbvd-mysql container (see ../lbvd-db/up.sh).
set -euo pipefail
cd "$(dirname "$0")"

exec uvicorn app.main:app \
  --host "${HOST:-127.0.0.1}" \
  --port "${PORT:-5000}"
