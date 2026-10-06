#!/usr/bin/env bash
# =============================================================================
# Cusin Gallery production restore (Phase E) -- the tested procedure that
# docs/DEPLOY.md's backup section refers to.
#
# USAGE:
#   scripts/restore.sh /var/backups/cusin/db/db-STAMP.dump \
#                      [/var/backups/cusin/media/media-STAMP.tar.gz]
#
# What it does:
#   1. Asks for explicit confirmation (this OVERWRITES the live database).
#   2. pg_restore --clean --if-exists into the running db service.
#   3. Optionally replaces the media volume contents from the tarball.
#
# IMPORTANT -- after a restore across releases:
#   If the backup predates newer code, run migrations afterwards:
#     docker compose -f docker-compose.prod.yml restart backend
#   (the production entrypoint applies `manage.py migrate` on start), or
#   better: restore a backup whose code version matches the checkout
#   (`git log` note in DEPLOY.md's rollback section).
#
# REHEARSE THIS. A restore you have never run is a hope, not a plan:
# DEPLOY.md's pre-launch checklist requires one full rehearsal on the
# server before opening the shop.
# =============================================================================
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
DB_DUMP="${1:?usage: restore.sh DB_DUMP [MEDIA_TARBALL]}"
MEDIA_TAR="${2:-}"

cd "$(dirname "$0")/.."

[ -f "$DB_DUMP" ] || { echo "ERROR: dump not found: $DB_DUMP" >&2; exit 1; }
if [ -n "$MEDIA_TAR" ]; then
    [ -f "$MEDIA_TAR" ] || { echo "ERROR: tarball not found: $MEDIA_TAR" >&2; exit 1; }
fi

set -a; . ./.env; set +a

echo "WARNING: this OVERWRITES database '$POSTGRES_DB' with $DB_DUMP"
[ -n "$MEDIA_TAR" ] && echo "WARNING: media files will be REPLACED from $MEDIA_TAR"
read -r -p "Type 'yes' to continue: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "aborted."
    exit 1
fi

echo "[restore] database ..."
# --clean --if-exists drops existing objects first; --no-owner avoids
# role-mismatch errors when the dump was made by another role name.
# pg_restore exits non-zero for harmless "already dropped" notices under
# --clean, so failures are reported but reviewed rather than fatal here.
docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --clean --if-exists --no-owner \
    < "$DB_DUMP" \
    || echo "[restore] pg_restore reported warnings/errors above -- review them (with --clean some are expected)."

if [ -n "$MEDIA_TAR" ]; then
    echo "[restore] media ..."
    docker compose -f "$COMPOSE_FILE" run --rm -T --no-deps \
        -v "$(dirname "$MEDIA_TAR"):/backup:ro" \
        backend sh -c "rm -rf /app/media/* && tar xzf '/backup/$(basename "$MEDIA_TAR")' -C /app/media"
fi

echo "[restore] done. Restart the backend so it re-applies any pending migrations:"
echo "  docker compose -f $COMPOSE_FILE restart backend"
