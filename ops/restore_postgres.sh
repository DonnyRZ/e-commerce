#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL must be set}"
: "${BACKUP_FILE:?BACKUP_FILE must point to a custom-format pg_dump file}"
if [ "${CONFIRM_RESTORE:-}" != "YES" ]; then
  echo "Refusing restore. Set CONFIRM_RESTORE=YES after verifying the target database." >&2
  exit 2
fi

pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" "$BACKUP_FILE"
printf 'Restore completed from %s\n' "$BACKUP_FILE"
