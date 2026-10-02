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

# System dependencies needed to build psycopg2-binary and Pillow (added in
# a later phase) on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/staticfiles /app/media

EXPOSE 8000

# Collects static files at container start (not build time) so a fresh
# volume/host mount always has current assets even if the image itself
# is reused. Migrations are run explicitly by the operator, not
# automatically on every container start, per "no fake/automatic schema
# changes" from the project requirements.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
