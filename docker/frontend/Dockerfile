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
# start time.
ARG VITE_API_BASE_URL=https://cusin.ir/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY frontend/package.json frontend/package-lock.json* ./
# Reproducibility note: `npm ci` requires a committed package-lock.json and
# is what production builds should use (exact resolved versions + integrity
# hashes, not just semver ranges). No lockfile is committed in this Phase 1
# handoff -- it could not be generated here (this sandbox has no npm
# registry access to resolve real versions or compute real integrity
# hashes), and a hand-written lockfile would be worse than none: it would
# *look* reproducible while actually being fabricated.
#
# Run `npm install` once on a machine with network access, commit the
# resulting frontend/package-lock.json, and this step automatically
# switches to `npm ci` on the next build -- no Dockerfile change needed.
# package.json now pins exact versions (no ^ ranges) in the meantime, which
# is a real, if weaker, reproducibility guarantee until that lockfile exists.
RUN if [ -f package-lock.json ]; then \
        echo "package-lock.json found -- using npm ci" && npm ci --no-audit --no-fund; \
    else \
        echo "No package-lock.json yet -- using npm install (see comment above)" && npm install --no-audit --no-fund; \
    fi

COPY frontend/ .
RUN npm run build

# --- Serve stage ---------------------------------------------------------------
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
