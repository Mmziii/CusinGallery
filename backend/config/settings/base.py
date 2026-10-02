"""
Base Django settings for the Cusin Gallery backend.

This file holds everything that is identical between development and
production. Environment-specific behaviour (DEBUG, security headers,
allowed hosts, etc.) lives in development.py / production.py, which both
import * from this module.

Nothing in this file should read os.environ directly for values that
differ between environments -- put that override in the environment
specific settings file instead.
"""
import os
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# base.py -> settings -> config -> backend (BASE_DIR)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------
env = environ.Env()

# Load backend/.env if present. In Docker Compose, variables are injected
# directly into the container environment instead, so a missing .env file
# here is not an error.
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("SECRET_KEY", default="unsafe-development-secret-key-do-not-use-in-production")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_filters",
]

# Local apps. Each is a clean foundation in Phase 1 -- business models and
# logic are added to these in later phases (see each app's models.py).
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.categories",
    "apps.products",
    "apps.cart",
    "apps.wishlist",
    "apps.discounts",
    "apps.orders",
    "apps.payments",
    "apps.reviews",
    "apps.banners",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# PostgreSQL only -- SQLite is intentionally not supported, including for
# local development, so that behaviour never silently diverges between
# environments. DATABASE_URL takes priority; if it's not set, we fall back
# to the discrete POSTGRES_* variables (handy for docker-compose).
if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="cusin_gallery"),
            "USER": env("POSTGRES_USER", default="cusin_user"),
            "PASSWORD": env("POSTGRES_PASSWORD", default="cusin_password"),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
        }
    }
DATABASES["default"]["CONN_MAX_AGE"] = 600

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
# apps.accounts.User (a custom user model) will be introduced in Phase 3.
# AUTH_USER_MODEL is declared here now, ahead of time, because switching it
# after the first migration is created is destructive -- so the foundation
# must commit to it from day one even though the model body is added later.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
# Authentication choice (Phase 3): session + CSRF, not token/JWT.
#
# Why: this project's own architecture already puts the frontend and the
# API on the same origin -- Nginx serves both cusin.ir/ (React build) and
# cusin.ir/api/ from one edge (see nginx/conf.d/cusin.conf). That's exactly
# the case session auth is the safer default for: httponly session cookies
# can't be read by JS at all (so they're not exposed to XSS the way a JWT
# stored in localStorage/sessionStorage would be), Django's session
# framework is a mature, well-audited part of the framework rather than
# extra machinery to maintain, and CSRF -- session auth's one real
# extra requirement -- was already fully wired in Phase 1
# (CsrfViewMiddleware, CSRF_TRUSTED_ORIGINS, CSRF_COOKIE_SAMESITE). JWT's
# usual justification (statelessness for a separate API domain, or native
# mobile clients with no cookie jar) doesn't apply here; adding it anyway
# would mean maintaining two auth systems for one that's actually needed.
#
# rest_framework.authtoken (present in Phase 1/2 as an unused placeholder)
# is removed as of this phase for the same reason -- an inert, unused
# second auth backend is exactly the "add multiple systems for
# completeness" anti-pattern this decision is meant to avoid.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DATETIME_FORMAT": "iso-8601",
    # Scoped, not blanket: rest_framework.throttling.ScopedRateThrottle only
    # throttles a view that explicitly sets `throttle_scope`, so this has
    # zero effect on any endpoint that doesn't opt in -- see
    # apps/accounts/views.py for which ones do (register, login,
    # password-reset request) and why those specifically need it.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "register": "10/hour",
        "login": "10/min",
        "password_reset": "5/hour",
        # Separate scope from the request endpoint -- see
        # PasswordResetConfirmView for why they must not share a quota.
        "password_reset_confirm": "10/hour",
        "checkout": "20/hour",
        # Payment initiation creates a gateway attempt per call -- same
        # abuse shape as checkout (both turn intent into persisted rows).
        "payment_initiate": "20/hour",
    },
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Filtered defensively: an env value of "" would otherwise parse to [""]
# rather than [] depending on the env-parsing library's exact behaviour,
# which would defeat the "must be non-empty in production" check in
# production.py.
CORS_ALLOWED_ORIGINS = [o for o in env.list("CORS_ALLOWED_ORIGINS", default=[]) if o]
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# Dev/test default: per-process LocMem. Fine for the single-process dev
# server and for tests (which clear it per test -- see
# apps/core/testing.py, and why that matters for DRF throttle counters).
#
# NOT fine for production: gunicorn runs several worker PROCESSES, each
# with its own LocMem instance, so DRF throttle hits (and any other
# cached state) would fragment per worker -- a rate limit of 20/hour
# would effectively allow 20/hour per worker, non-deterministically.
# Production therefore swaps in one shared Redis instance -- see
# config/settings/production.py.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "cusin-gallery",
    }
}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@cusin.ir")

# ---------------------------------------------------------------------------
# Payment gateway (Phase C - real payments; see apps/payments + docs/PAYMENTS.md)
# ---------------------------------------------------------------------------
# Gateway selection. "mock" (or empty) = the self-contained MockGateway
# for development/tests -- config/settings/production.py REFUSES to start
# with it, so it is impossible to enable in production. "zarinpal" = the
# real ZarinPal PSP adapter. Unknown values fail loudly (ImproperlyConfigured)
# the moment any payment flow runs. Adding another PSP = one new adapter
# class + one registry line (docs/PAYMENTS.md explains how).
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", default="")

# ZarinPal: the 36-character merchant id from the ZarinPal merchant panel.
# Required whenever PAYMENT_GATEWAY=zarinpal (production.py enforces).
# The mock gateway reuses this slot as its HMAC callback-signing secret
# (falling back to SECRET_KEY when empty) -- in both cases server-side
# only, never sent to the browser.
PAYMENT_MERCHANT_ID = env("PAYMENT_MERCHANT_ID", default="")

# ZarinPal mode switch. True = sandbox.zarinpal.com (full test mode: any
# 36-character merchant id is accepted, no real money moves). False =
# production (api.zarinpal.com + www.zarinpal.com). Sandbox/production
# differ ONLY by the hosts the adapter talks to.
PAYMENT_ZARINPAL_SANDBOX = env.bool("PAYMENT_ZARINPAL_SANDBOX", default=False)

# Absolute URL of this backend's callback endpoint -- where the gateway
# sends the customer's browser back after payment. Served at BOTH
# /payment/callback/ and /api/v1/payments/callback/ (same view). When
# payments are initiated through the API view, the callback URL is built
# from the incoming request instead (correct on any origin); this env
# value is the fallback for programmatic initiation and the documented
# value to register in the PSP's merchant panel.
PAYMENT_CALLBACK_URL = env("PAYMENT_CALLBACK_URL", default="https://cusin.ir/payment/callback/")

# Seconds to wait for a gateway HTTP call (payment request + verify)
# before treating the gateway as unreachable (GatewayError).
PAYMENT_GATEWAY_TIMEOUT = env.int("PAYMENT_GATEWAY_TIMEOUT", default=15)

# ---------------------------------------------------------------------------
# Frontend URL (Phase 3)
# ---------------------------------------------------------------------------
# Used only to build absolute links that point at the React app from
# backend-generated content -- currently just the password-reset email
# (see apps/accounts/views.py's PasswordResetRequestView). Not used for
# CORS/CSRF, which are configured separately and already cover this same
# origin (see CORS_ALLOWED_ORIGINS / CSRF_TRUSTED_ORIGINS above).
FRONTEND_URL = env("FRONTEND_URL", default="https://cusin.ir")

# ---------------------------------------------------------------------------
# Shipping (Phase 6; selectable methods + delivery windows added in the
# Phase A corrections round)
# ---------------------------------------------------------------------------
# All shipping numbers live here (config), never hardcoded in
# apps/orders/shipping.py or scattered across views/serializers -- that
# module reads only these settings. Orders SNAPSHOT the method, cost and
# delivery window at checkout time (Order.shipping_method /
# estimated_delivery_min / estimated_delivery_max), so later changes to
# these values never rewrite history -- see apps/orders/models.py.
STANDARD_SHIPPING_COST = env.int("STANDARD_SHIPPING_COST", default=50000)
FREE_SHIPPING_THRESHOLD = env.int("FREE_SHIPPING_THRESHOLD", default=1000000)

# Estimated delivery window (calendar days from the order date) for the
# standard method.
SHIPPING_MIN_DELIVERY_DAYS = env.int("SHIPPING_MIN_DELIVERY_DAYS", default=3)
SHIPPING_MAX_DELIVERY_DAYS = env.int("SHIPPING_MAX_DELIVERY_DAYS", default=5)

# Express method: fixed cost (never free -- the free-shipping threshold
# is a standard-delivery promotion and deliberately does NOT apply here),
# with its own faster window.
EXPRESS_SHIPPING_COST = env.int("EXPRESS_SHIPPING_COST", default=90000)
EXPRESS_MIN_DELIVERY_DAYS = env.int("EXPRESS_MIN_DELIVERY_DAYS", default=1)
EXPRESS_MAX_DELIVERY_DAYS = env.int("EXPRESS_MAX_DELIVERY_DAYS", default=2)

# The selectable shipping methods offered at checkout. Cost and delivery
# window per method are all env-configurable above. `free_threshold` is
# None when the method is never free. New methods = a new entry here (plus
# its settings); apps/orders/shipping.py and the checkout flow need no
# change -- they only ever read this dict.
SHIPPING_METHODS = {
    "standard": {
        "cost": STANDARD_SHIPPING_COST,
        "free_threshold": FREE_SHIPPING_THRESHOLD,
        "min_days": SHIPPING_MIN_DELIVERY_DAYS,
        "max_days": SHIPPING_MAX_DELIVERY_DAYS,
    },
    "express": {
        "cost": EXPRESS_SHIPPING_COST,
        "free_threshold": None,
        "min_days": EXPRESS_MIN_DELIVERY_DAYS,
        "max_days": EXPRESS_MAX_DELIVERY_DAYS,
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Dedicated logger for payment-related events. Never log secrets,
        # card data, or full gateway payloads through this logger -- see
        # apps/payments (Phase 7) for the logging policy.
        "payments": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
