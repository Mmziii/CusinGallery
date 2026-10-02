"""
Development settings.

Run with:
    DJANGO_SETTINGS_MODULE=config.settings.development python manage.py runserver

This is also the default manage.py falls back to when DJANGO_SETTINGS_MODULE
is not set at all, so a bare `python manage.py runserver` on a laptop never
accidentally boots with production settings.
"""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Same env-driven trust list as production (see production.py) so that
# preview/tunnel origins (e.g. https://*.e2b.app) can be added per
# environment without code changes. Empty by default -- when the SPA is
# served same-origin behind a proxy Django already accepts Origins that
# match the request Host.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Preview tunnels (e.g. https://{port}-{sandbox}.e2b.app) terminate TLS
# before requests reach the dev server; trust the edge's proto header so
# request.is_secure() / build_absolute_uri() produce https URLs. Mirrors
# production.py's setting -- harmless on plain localhost, where the
# header is simply absent.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Permissive CORS locally so the Vite dev server (default: localhost:5173)
# can talk to the API without needing exact origin configuration every time
# a teammate uses a different port. Production is locked down instead --
# see production.py.
CORS_ALLOW_ALL_ORIGINS = True

# Emails are printed to the console instead of actually sent, so no SMTP
# credentials are needed for day-to-day development.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Django's default DEBUG=True error pages are enough locally; no extra
# security headers are forced on here.
