#!/bin/sh
set -e

# Production တွင် ဝင်ရောက်လာသော request �들을 worker များဆီသို့ မျှဝေပေးရန်
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 5000 \
    --workers "${WEB_CONCURRENCY:-16}" \
    --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-172.16.0.0/12}" \
    --proxy-headers