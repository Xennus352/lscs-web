#!/usr/bin/env bash
# Backup the LBVD database from the DB VM (192.168.111.100).
#
#   ./deploy/three-tier/backup-db.sh
#
# Nightly cron (root):
#   15 2 * * * /srv/lbvd/deploy/three-tier/backup-db.sh >> /var/log/lbvd-backup.log 2>&1
#
# Keep a copy on another machine: a backup on the same disk/VM is not a backup.
set -euo pipefail
cd "$(dirname "$0")/../.."

mkdir -p backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="backups/lbvd-${stamp}.sql.gz"

docker compose --env-file .env.db -f docker-compose.db.yml exec -T db \
  sh -c 'exec mariadb-dump --single-transaction --quick --routines --triggers \
    -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' \
  | gzip > "$out"

if [ ! -s "$out" ]; then
  echo "backup failed: empty dump: $out" >&2
  exit 1
fi

# 14 daily files.
find backups -name 'lbvd-*.sql.gz' -mtime +14 -delete
echo "wrote $out ($(du -h "$out" | cut -f1))"
