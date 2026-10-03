#!/usr/bin/env bash
# =============================================================================
# Cusin Gallery production backup (Phase E).
#
# What it does:
#   1. pg_dump (custom -Fc format, compressed, restorable selectively) of the
#      PostgreSQL database, taken THROUGH the compose `db` service -- no port
#      is exposed, so this is the only supported path.
#   2. tar.gz of the media volume (product/banner/category images, user
#      uploads) via a one-shot backend container that has the volume mounted.
#   3. Rotation: files older than KEEP_DAYS are deleted.
#
# Storage: NEVER inside the git repository. Default target is
# /var/backups/cusin (outside the checkout); override with BACKUP_DIR.
# Copy the result OFF the server too (object storage / another machine) --
# a backup on the same disk as the data is only half a backup.
#
# Cron example (daily at 03:15, logged):
#   15 3 * * * cd /opt/cusin/CusinGallery && ./scripts/backup.sh >> /var/log/cusin-backup.log 2>&1
#
# Env overrides: COMPOSE_FILE, BACKUP_DIR, KEEP_DAYS.
# =============================================================================
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/cusin}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "ERROR: .env not found next to $COMPOSE_FILE -- run from the deployment root." >&2
    exit 1
fi
# Read POSTGRES_* the same way compose does.
set -a; . ./.env; set +a

mkdir -p "$BACKUP_DIR/db" "$BACKUP_DIR/media"

echo "[backup] $STAMP dumping database ${POSTGRES_DB} ..."
docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
    > "$BACKUP_DIR/db/db-$STAMP.dump"

echo "[backup] $STAMP archiving media volume ..."
docker compose -f "$COMPOSE_FILE" run --rm -T --no-deps \
    -v "$BACKUP_DIR/media:/backup" \
    backend tar czf "/backup/media-$STAMP.tar.gz" -C /app/media .

echo "[backup] rotating: deleting files older than $KEEP_DAYS day(s) ..."
find "$BACKUP_DIR/db"    -name 'db-*.dump'      -mtime +"$KEEP_DAYS" -print -delete
find "$BACKUP_DIR/media" -name 'media-*.tar.gz' -mtime +"$KEEP_DAYS" -print -delete

# Fail loudly if the dump is empty (e.g. pg_dump errored but the redirect
# still created a file): a 0-byte "backup" is worse than none.
if [ ! -s "$BACKUP_DIR/db/db-$STAMP.dump" ]; then
    echo "ERROR: database dump is empty -- backup FAILED." >&2
    rm -f "$BACKUP_DIR/db/db-$STAMP.dump"
    exit 1
fi

echo "[backup] done: $BACKUP_DIR/db/db-$STAMP.dump + $BACKUP_DIR/media/media-$STAMP.tar.gz"
