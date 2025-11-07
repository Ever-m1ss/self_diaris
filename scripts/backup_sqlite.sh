#!/usr/bin/env bash
set -euo pipefail

# Simple timestamped backup for SQLite database.
# Stores backups under backups/ with gzip compression.
# Keeps last N backups (default 10) and prunes older ones.

KEEP=${KEEP_BACKUPS:-10}
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_FILE="$PROJECT_DIR/db.sqlite3"
BACKUP_DIR="$PROJECT_DIR/backups"
mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_FILE" ]; then
  echo "Database file not found: $DB_FILE" >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/db-$TS.sqlite3.gz"
echo "Creating backup: $OUT"
gzip -c "$DB_FILE" > "$OUT"

echo "Pruning old backups, keep last $KEEP"
ls -1t "$BACKUP_DIR"/db-*.sqlite3.gz | tail -n +$((KEEP+1)) | xargs -r rm -f

echo "Backup complete." 
