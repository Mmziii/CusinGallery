"""
ASGI config for the Cusin Gallery backend.

Not used by the production deployment path in Phase 1 (Gunicorn+WSGI is),
but kept present so async features (e.g. websocket order-status updates)
can be added later without restructuring the project.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_asgi_application()
