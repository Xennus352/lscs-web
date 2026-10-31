#!/usr/bin/env bash
# Dump the production database to ./backups and keep the last 14 daily files.
#
#   ./deploy/backup.sh
#
# Add to root's crontab for a nightly backup:
#   15 2 * * * /path/to/LBVDProject/deploy/backup.sh >> /var/log/lbvd-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"

docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  sh -c 'exec mariadb-dump --single-transaction --routines --triggers \
    -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' \
  | gzip > "backups/lbvd-${stamp}.sql.gz"

# Abort (and keep the partial file for inspection) if the dump is empty.
if [ ! -s "backups/lbvd-${stamp}.sql.gz" ]; then
  echo "backup failed: empty dump" >&2
  exit 1
fi

find backups -name 'lbvd-*.sql.gz' -mtime +14 -delete
echo "wrote backups/lbvd-${stamp}.sql.gz"
