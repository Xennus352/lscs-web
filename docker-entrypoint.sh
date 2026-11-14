#!/bin/sh
set -e

# Production တွင် ဝင်ရောက်လာသော request များကို worker များဆီသို့ မျှဝေပေးရန်
# WEB_CONCURRENCY ကို VM ၏ CPU core အရ သတ်မှတ်နိုင်သည် (default 16).
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 5000 \
    --workers "${WEB_CONCURRENCY:-16}" \
    --limit-concurrency "${WEB_CONCURRENCY_LIMIT:-1200}" \
    --backlog "${WEB_BACKLOG:-2048}" \
    --timeout-keep-alive "${WEB_TIMEOUT_KEEP_ALIVE:-30}" \
    --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-172.16.0.0/12}" \
    --proxy-headers
