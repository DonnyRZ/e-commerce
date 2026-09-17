#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL must be set}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

pg_dump "$DATABASE_URL" --format=custom --file="$BACKUP_DIR/marketplace-$STAMP.dump"
printf 'Backup written to %s\n' "$BACKUP_DIR/marketplace-$STAMP.dump"
