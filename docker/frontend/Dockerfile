# Multi-stage build: compile the React app, then serve the static output
# with a minimal nginx. This container is an internal upstream only -- the
# top-level nginx/ service (see nginx/conf.d/cusin.conf) is the one edge
# reverse proxy that actually terminates cusin.ir / www.cusin.ir traffic
# and forwards page requests here and API requests to the backend.
#
# NOTE: build context for this Dockerfile is the REPOSITORY ROOT, not
# frontend/ -- see docker-compose.yml (`context: .`). That's required so
# this Dockerfile can COPY docker/frontend/nginx.conf alongside the
# frontend/ source in the same build. All COPY paths below are written
# relative to the repo root accordingly.

# --- Build stage -------------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# VITE_API_BASE_URL must be supplied as a build arg (see docker-compose.yml)
# because Vite inlines VITE_* variables at build time, not at container
# start time. Default: same-origin "/api/v1" -- nginx routes /api/ to the
# backend, so no cross-origin configuration is needed.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# VITE_SITE_ORIGIN (Phase E): the canonical public origin used by
# src/hooks/usePageMeta.js to build <link rel=canonical> and og:url
# values. Default matches the production domain; a staging deployment
# overrides it via compose args / .env (see docker-compose.prod.yml).
ARG VITE_SITE_ORIGIN=https://cusin.ir
ENV VITE_SITE_ORIGIN=${VITE_SITE_ORIGIN}

# VITE_SENTRY_DSN (Part S3 item 9): non-empty = the storefront's
# ErrorBoundary posts crash reports to /api/v1/site/report-error/, which
# forwards them into the backend's Sentry. Empty default = the browser
# never sends anything.
ARG VITE_SENTRY_DSN=
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}

COPY frontend/package.json frontend/package-lock.json* ./

# Optional: a local/enterprise npm registry for networks where
# registry.npmjs.org is slow or blocked. Empty by default -- no mirror is
# assumed or hard-coded (npm's own NPM_CONFIG_REGISTRY env var works the
# same way, but a build arg is what Compose can pass per machine):
#   docker build --build-arg NPM_CONFIG_REGISTRY=https://<your-mirror>/ ...
ARG NPM_CONFIG_REGISTRY

# Reproducibility: frontend/package-lock.json is committed, so this uses
# `npm ci` (exact resolved versions + integrity hashes). If the lockfile
# is ever missing (e.g. a partial checkout), it falls back to
# `npm install`.
#
# This is the ONLY step in either Dockerfile that talks to a package
# registry at build time (the backend image installs wheels from PyPI and
# nothing else does network I/O), so it is also the only one a mirror can
# matter for. Build-time network still needed regardless of mirror: the
# base images below, which can be pre-pulled -- see docs/DEPLOY.md.
RUN if [ -f package-lock.json ]; then \
        echo "package-lock.json found -- using npm ci" && npm ci --no-audit --no-fund ${NPM_CONFIG_REGISTRY:+--registry=${NPM_CONFIG_REGISTRY}}; \
    else \
        echo "No package-lock.json -- falling back to npm install" && npm install --no-audit --no-fund ${NPM_CONFIG_REGISTRY:+--registry=${NPM_CONFIG_REGISTRY}}; \
    fi

COPY frontend/ .
RUN npm run build

# --- Serve stage ---------------------------------------------------------------
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
