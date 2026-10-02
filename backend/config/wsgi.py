"""
WSGI config for the Cusin Gallery backend.

Used by Gunicorn in production (see docker/backend/Dockerfile) and
available for any other WSGI-compatible server.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_wsgi_application()
