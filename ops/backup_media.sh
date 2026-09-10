#!/usr/bin/env sh
set -eu

: "${MEDIA_ROOT:?MEDIA_ROOT must point to the media directory}"
BACKUP_DIR="${MEDIA_BACKUP_DIR:-./backups/media}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

ARCHIVE="$BACKUP_DIR/media-$STAMP.tar.gz"
tar -czf "$ARCHIVE" -C "$MEDIA_ROOT" .
printf 'Media backup written to %s\n' "$ARCHIVE"
