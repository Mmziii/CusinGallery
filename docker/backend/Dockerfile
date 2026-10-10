# Production image for the Django backend. Served by Gunicorn; Nginx
# (see nginx/conf.d/cusin.conf) sits in front of this container and also
# serves /static/ and /media/ directly rather than proxying them here.
FROM python:3.12-slim

# Prevents Python from buffering stdout/stderr, so logs appear immediately
# in `docker compose logs` instead of being held in a buffer.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# NO apt-get here, on purpose. This image used to install libpq-dev + gcc
# "to build psycopg2-binary and Pillow on slim images", but both ship
# prebuilt manylinux wheels for CPython 3.12 (and so does every other
# requirement, direct or transitive), so nothing in this image is ever
# compiled. The step also made every build depend on deb.debian.org being
# reachable -- which failed for real on a network where the Debian mirrors
# are blocked, even though the build needs nothing from them.
# Verified (see the report / docs/DEPLOY.md "نصب روی شبکههای محدود"):
#   pip download --only-binary=:all: --python-version 3.12 \
#       --implementation cp --abi cp312 --platform manylinux2014_x86_64 \
#       -r requirements.txt
# downloads 24 wheels and no source archives, and psycopg2-binary bundles
# its own libpq (psycopg2_binary.libs/libpq-*.so.5), so libpq-dev is not
# needed at build OR run time.
COPY requirements.txt .

# Optional: a local/enterprise PyPI mirror for networks where pypi.org is
# slow or blocked. Empty by default -- no mirror is assumed or hard-coded:
#   docker build --build-arg PIP_INDEX_URL=https://<your-mirror>/simple/ ...
# --only-binary=:all: is deliberate: with no compiler in the image, a
# requirement that suddenly had no wheel must fail loudly here instead of
# silently falling back to a source build that cannot work.
ARG PIP_INDEX_URL
RUN pip install --no-cache-dir --only-binary=:all: \
        ${PIP_INDEX_URL:+--index-url=${PIP_INDEX_URL}} \
        -r requirements.txt

COPY . .

RUN mkdir -p /app/staticfiles /app/media

EXPOSE 8000

# Collects static files at container start (not build time) so a fresh
# volume/host mount always has current assets even if the image itself
# is reused. Migrations are run explicitly by the operator, not
# automatically on every container start, per "no fake/automatic schema
# changes" from the project requirements.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 300 --graceful-timeout 300"]
