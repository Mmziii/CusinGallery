#!/bin/sh
# Production backend entrypoint (Phase E).
#
# Mounted read-only into the backend container by docker-compose.prod.yml
# (the image itself keeps its plain gunicorn CMD for the dev compose, so
# nothing about local development changes).
#
# Deploy-time behaviour required by Phase E: migrations and collectstatic
# run AUTOMATICALLY on every (re)deploy, then gunicorn takes over via exec
# (signals reach gunicorn directly -- clean reloads/shutdowns for docker).
#
# Single-replica assumption: this stack runs ONE backend container, so
# "migrate on start" cannot race with another replica. If the deployment
# ever scales backend horizontally, move `migrate` out of this script into
# an explicit one-shot deploy step (docker compose run --rm backend
# python manage.py migrate) BEFORE rolling the replicas.
#
# Tuning: GUNICORN_WORKERS, GUNICORN_TIMEOUT (seconds -- the hard ceiling on
# how long one request may run before its worker is killed) and
# GUNICORN_GRACEFUL_TIMEOUT are read from the environment, so a slow box can
# be given more headroom without rebuilding the image. The timeout default
# is 120s, not the old 60s: the admin's bulk operations (notably the image
# ZIP import) legitimately run longer than a minute on the 1-vCPU server,
# and a killed worker used to surface as a bare 502 with no explanation.
#
# Failure policy: `set -e` -- a failed migration or collectstatic must
# stop the container (restart policy will retry and the operator sees it
# in `docker compose logs backend`). Serving traffic against a
# half-migrated database is exactly what we must never do.
set -e

echo "[entrypoint] $(date -u +%FT%TZ) applying database migrations..."
python manage.py migrate --noinput

echo "[entrypoint] collecting static files..."
python manage.py collectstatic --noinput

echo "[entrypoint] starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-30}" \
    --access-logfile - \
    --error-logfile -
