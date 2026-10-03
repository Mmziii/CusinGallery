"""
Production settings.

Deploy with:
    DJANGO_SETTINGS_MODULE=config.settings.production

Everything security-sensitive that should NEVER be true in an environment
reachable from the internet is forced here, deliberately duplicated rather
than relying only on defaults, so a missing environment variable fails
closed (secure) instead of failing open (insecure).
"""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["cusin.ir", "www.cusin.ir"])

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["https://cusin.ir", "https://www.cusin.ir"]
)

# CORS must be an explicit allow-list in production -- never wildcard.
CORS_ALLOW_ALL_ORIGINS = False
if not CORS_ALLOWED_ORIGINS:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS is empty. Set it explicitly in production "
        "(e.g. https://cusin.ir,https://www.cusin.ir) -- refusing to start "
        "with no allowed frontend origins."
    )
if "*" in CORS_ALLOWED_ORIGINS:
    # A bare "*" would let ANY origin make credentialed requests against
    # the session-authenticated API. The same-origin deployment needs no
    # wildcard at all (see the REST_FRAMEWORK auth comment in base.py).
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS contains a bare '*' wildcard. Production "
        "requires an explicit origin allow-list -- refusing to start."
    )

# --- Shared cache (Redis) ----------------------------------------------------
# DRF throttling stores hit counters in the Django cache. Gunicorn workers
# are separate processes, so base.py's per-process LocMem cache would
# fragment every rate limit per worker (see the CACHES comment there).
# Production must point all workers at ONE shared Redis instance -- the
# default below matches the compose service name in docker-compose.yml.
# Uses Django's built-in RedisCache backend (requires the `redis` client
# package), not django-redis.
REDIS_URL = env("REDIS_URL", default="redis://redis:6379/1")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# --- HTTPS toggle -------------------------------------------------------------
# Everything below that depends on HTTPS actually being live (secure-only
# cookies, forcing a redirect to https://) is gated behind this ONE flag,
# defaulting to False.
#
# Why default False: nginx/conf.d/cusin.conf currently only has an HTTP
# (port 80) server block -- no certificate exists yet (see Phase 1 README).
# If SECURE_SSL_REDIRECT defaulted to True here, every request would be
# redirected to an https:// endpoint nginx doesn't serve yet -- a broken
# deployment, not a security improvement. Likewise, SESSION_COOKIE_SECURE /
# CSRF_COOKIE_SECURE = True would make browsers silently refuse to send
# those cookies over the plain HTTP that's actually live, breaking login
# and CSRF-protected requests entirely.
#
# Once real certificates are obtained and the HTTPS server block in
# nginx/conf.d/cusin.conf is uncommented (see that file), set
# HTTPS_ENABLED=True in the environment. No code changes are needed beyond
# that -- SECURE_PROXY_SSL_HEADER below is already correctly configured
# for nginx's proxy headers either way.
HTTPS_ENABLED = env.bool("HTTPS_ENABLED", default=False)

# --- Cookies & transport security ------------------------------------------
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Django needs this readable by JS for the CSRF header pattern
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_SSL_REDIRECT = HTTPS_ENABLED
# Nginx terminates TLS and forwards to Gunicorn over plain HTTP inside the
# Docker network -- this header is what tells Django the original request
# was HTTPS. Safe to leave set even while HTTPS_ENABLED is False: nginx's
# HTTP-only server block always forwards X-Forwarded-Proto: http right now
# (see nginx/conf.d/cusin.conf), so request.is_secure() correctly evaluates
# False either way -- this line only matters once the HTTPS block is live.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HSTS tells browsers to refuse HTTP entirely for this domain, for
# SECURE_HSTS_SECONDS going forward -- genuinely dangerous to send before
# HTTPS is confirmed working, since a mistake would lock out real users
# with no HTTP fallback until the header value expires. Gated on
# HTTPS_ENABLED as an explicit belt-and-suspenders on top of
# SECURE_PROXY_SSL_HEADER already making the Django-level HSTS logic
# correctly inert over HTTP.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000) if HTTPS_ENABLED else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS_ENABLED
SECURE_HSTS_PRELOAD = HTTPS_ENABLED

SECURE_CONTENT_TYPE_NOSNIFF = True
# NOTE: no X-XSS-Protection header here on purpose -- the header is
# deprecated/ignored by modern browsers and the Django setting that
# emitted it (SECURE_BROWSER_XSS_FILTER) was removed in Django 5.
# XSS safety comes from Django's template/JSON escaping and
# X-Content-Type-Options above.
X_FRAME_OPTIONS = "DENY"

# --- Fail loudly on missing secrets -----------------------------------------
# Covers both cases: the variable left completely unset (env() returns the
# development default) AND the variable present but empty, e.g. a template
# `.env` copied over with `SECRET_KEY=` never filled in -- env-file tools
# return "" for that, not the default, so both must be checked explicitly.
if not SECRET_KEY or SECRET_KEY == "unsafe-development-secret-key-do-not-use-in-production":
    raise RuntimeError(
        "SECRET_KEY is not set (or is empty). Refusing to start with an "
        "unsafe/missing key in a production settings module. Set a real "
        "SECRET_KEY in the environment (see .env.example)."
    )

# --- The mock payment gateway must be impossible in production ---------------
# apps.payments ships a MockGateway for development and tests. An empty
# PAYMENT_GATEWAY means the same thing (the registry's default), so both
# are refused here: a production deployment must explicitly name a real
# PSP. See docs/PAYMENTS.md for the sandbox -> production runbook.
_payment_gateway = (PAYMENT_GATEWAY or "mock").strip().lower()
if _payment_gateway == "mock":
    raise RuntimeError(
        "PAYMENT_GATEWAY is unset or 'mock'. The mock payment gateway is "
        "for development/tests only and cannot be enabled in production. "
        "Set PAYMENT_GATEWAY=zarinpal (plus PAYMENT_MERCHANT_ID) in the "
        "environment -- see .env.example and docs/PAYMENTS.md."
    )
if _payment_gateway == "zarinpal" and not PAYMENT_MERCHANT_ID.strip():
    raise RuntimeError(
        "PAYMENT_GATEWAY=zarinpal but PAYMENT_MERCHANT_ID is empty. Set "
        "the 36-character merchant id from the ZarinPal merchant panel "
        "(for sandbox testing any 36-character value is accepted -- see "
        "docs/PAYMENTS.md)."
    )

# --- The console SMS provider must be impossible in production --------------
# Same rule as the mock payment gateway: apps/notifications ships a
# log-only console provider for development/tests. With SMS features
# enabled (the default), production must name a real provider and its
# credentials; the only way to run production without SMS is the
# explicit, honest opt-out SMS_ENABLED=False (phone-only password resets
# then record a SKIPPED notification instead of pretending to send).
_sms_provider = (SMS_PROVIDER or "console").strip().lower()
if SMS_ENABLED:
    if _sms_provider == "console":
        raise RuntimeError(
            "SMS_PROVIDER is unset or 'console'. The console SMS provider only "
            "logs; it is for development/tests and cannot be enabled in "
            "production while SMS_ENABLED=True. Set SMS_PROVIDER=kavenegar "
            "(plus KAVENEGAR_API_KEY), or set SMS_ENABLED=False explicitly "
            "to run without SMS -- see .env.example."
        )
    if _sms_provider == "kavenegar" and not KAVENEGAR_API_KEY.strip():
        raise RuntimeError(
            "SMS_PROVIDER=kavenegar but KAVENEGAR_API_KEY is empty. Set the "
            "API key from the Kavenegar panel, or set SMS_ENABLED=False to "
            "run without SMS."
        )

# Production always sends real email via SMTP.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
