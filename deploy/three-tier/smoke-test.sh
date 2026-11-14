#!/usr/bin/env bash
# Quick checks for the three-VM layout. Run from any host that can reach all
# three addresses (usually the web server).
set -u

WEB=${WEB:-192.168.111.50}
API=${API:-192.168.111.200}
DB=${DB:-192.168.111.100}
fail=0

check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "OK   $label"
  else
    echo "FAIL $label"
    fail=1
  fi
}

check "web  /healthz"        curl -fsS --max-time 5 "http://${WEB}/healthz"
check "web  / (login page)"  curl -fsS --max-time 10 "http://${WEB}/"
check "api  /api/check-update" curl -fsS --max-time 5 "http://${API}:5000/api/check-update"
check "api  via web proxy"   curl -fsS --max-time 10 "http://${WEB}/api/check-update"

if command -v nc >/dev/null 2>&1; then
  check "db   3306 reachable" nc -z -w 5 "$DB" 3306
else
  echo "SKIP db 3306 (nc not installed)"
fi

exit "$fail"
