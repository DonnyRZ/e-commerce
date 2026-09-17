#!/usr/bin/env sh
set -eu

: "${MEDIA_ROOT:?MEDIA_ROOT must point to the media directory}"
: "${MEDIA_BACKUP_FILE:?MEDIA_BACKUP_FILE must point to a media archive}"
if [ "${CONFIRM_RESTORE:-}" != "YES" ]; then
  echo "Refusing media restore. Set CONFIRM_RESTORE=YES after verifying the target directory." >&2
  exit 2
fi

mkdir -p "$MEDIA_ROOT"
tar -xzf "$MEDIA_BACKUP_FILE" -C "$MEDIA_ROOT"
printf 'Media restore completed from %s\n' "$MEDIA_BACKUP_FILE"
