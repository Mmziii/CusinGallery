"""
Production settings audit (Phase E).

Locks in the security posture of config/settings/production.py as real,
tested behaviour instead of prose: DEBUG off, secrets/hosts/CORS from env
with fail-closed guards, cookie/HSTS flags following the single
HTTPS_ENABLED switch, the nginx proxy-header trust, locked-down CORS,
Redis-backed cache, SMTP email -- plus the Phase E additions: Sentry
initialization exactly when SENTRY_DSN is set, and the LOG_FORMAT
structured-logging switch.

Technique: the settings modules are (re-)imported under a patched
environment, exactly like apps/payments/tests/test_gateway_config.py --
see there for why the cleanup matters.
"""
import importlib
import os
import sys
from unittest import TestCase, mock

VALID_ENV = {
    "SECRET_KEY": "production-audit-test-key-not-the-dev-default",
    "CORS_ALLOWED_ORIGINS": "https://cusin.ir,https://www.cusin.ir",
    "ALLOWED_HOSTS": "cusin.ir,www.cusin.ir",
    "CSRF_TRUSTED_ORIGINS": "https://cusin.ir,https://www.cusin.ir",
    "PAYMENT_GATEWAY": "zarinpal",
    "PAYMENT_MERCHANT_ID": "c64a6c77-0000-4000-8000-000000000000",
    "SMS_PROVIDER": "kavenegar",
    "KAVENEGAR_API_KEY": "production-audit-test-kavenegar-key",
    "REDIS_URL": "redis://redis:6379/1",
    "EMAIL_HOST": "smtp.example.com",
}


def _import_modules(env):
    with mock.patch.dict(os.environ, env):
        base = importlib.import_module("config.settings.base")
        importlib.reload(base)
        production = importlib.import_module("config.settings.production")
        importlib.reload(production)
    return base, production


class ProductionSettingsAuditTests(TestCase):
    def setUp(self):
        base = importlib.import_module("config.settings.base")
        self.addCleanup(importlib.reload, base)
        self.addCleanup(sys.modules.pop, "config.settings.production", None)

    def _production(self, **overrides):
        env = dict(VALID_ENV)
        env.update(overrides)
        return _import_modules(env)[1]

    # --- the non-negotiables ---------------------------------------------------

    def test_debug_is_off(self):
        prod = self._production(DEBUG="True")  # even if the env lies
        self.assertFalse(prod.DEBUG)

    def test_hosts_and_csrf_come_from_env(self):
        prod = self._production()
        self.assertEqual(prod.ALLOWED_HOSTS, ["cusin.ir", "www.cusin.ir"])
        self.assertEqual(
            prod.CSRF_TRUSTED_ORIGINS, ["https://cusin.ir", "https://www.cusin.ir"]
        )

    def test_cors_is_locked_down(self):
        prod = self._production()
        self.assertFalse(prod.CORS_ALLOW_ALL_ORIGINS)
        self.assertEqual(
            prod.CORS_ALLOWED_ORIGINS, ["https://cusin.ir", "https://www.cusin.ir"]
        )

    def test_empty_or_wildcard_cors_env_is_refused(self):
        with self.assertRaises(RuntimeError):
            self._production(CORS_ALLOWED_ORIGINS="")
        with self.assertRaises(RuntimeError) as ctx:
            self._production(CORS_ALLOWED_ORIGINS="*")
        self.assertIn("wildcard", str(ctx.exception))

    def test_missing_or_default_secret_key_is_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._production(SECRET_KEY="")
        self.assertIn("SECRET_KEY", str(ctx.exception))
        with self.assertRaises(RuntimeError):
            self._production(
                SECRET_KEY="unsafe-development-secret-key-do-not-use-in-production"
            )

    def test_session_cookies_are_httponly_and_samesite_lax(self):
        prod = self._production()
        self.assertTrue(prod.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(prod.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(prod.CSRF_COOKIE_SAMESITE, "Lax")
        # Readable by JS on purpose: Django's CSRF header pattern needs it.
        self.assertFalse(prod.CSRF_COOKIE_HTTPONLY)

    def test_proxy_header_trust_is_configured_for_nginx(self):
        prod = self._production()
        self.assertEqual(prod.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_security_headers(self):
        prod = self._production()
        self.assertTrue(prod.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(prod.X_FRAME_OPTIONS, "DENY")

    # --- the single HTTPS switch ------------------------------------------------

    def test_https_disabled_is_the_safe_default(self):
        prod = self._production(HTTPS_ENABLED="False")
        self.assertFalse(prod.SESSION_COOKIE_SECURE)
        self.assertFalse(prod.CSRF_COOKIE_SECURE)
        self.assertFalse(prod.SECURE_SSL_REDIRECT)
        self.assertEqual(prod.SECURE_HSTS_SECONDS, 0)

    def test_https_enabled_turns_on_cookies_redirect_and_hsts(self):
        prod = self._production(HTTPS_ENABLED="True")
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)
        self.assertTrue(prod.SECURE_SSL_REDIRECT)
        self.assertEqual(prod.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(prod.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(prod.SECURE_HSTS_PRELOAD)

    # --- infrastructure -----------------------------------------------------------

    def test_cache_is_shared_redis_from_env(self):
        prod = self._production(REDIS_URL="redis://cache-host:6379/4")
        self.assertEqual(
            prod.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.redis.RedisCache",
        )
        self.assertEqual(prod.CACHES["default"]["LOCATION"], "redis://cache-host:6379/4")

    def test_email_backend_is_smtp_in_production(self):
        prod = self._production()
        self.assertEqual(
            prod.EMAIL_BACKEND, "django.core.mail.backends.smtp.EmailBackend"
        )


class StructuredLoggingTests(TestCase):
    def setUp(self):
        base = importlib.import_module("config.settings.base")
        self.addCleanup(importlib.reload, base)

    def test_default_is_the_plain_formatter(self):
        env = dict(VALID_ENV)
        env.pop("LOG_FORMAT", None)
        base, _ = _import_modules(env)
        self.assertEqual(base.LOGGING["handlers"]["console"]["formatter"], "verbose")

    def test_log_format_json_switches_the_console_handler(self):
        base, _ = _import_modules({**VALID_ENV, "LOG_FORMAT": "json"})
        self.assertEqual(base.LOGGING["handlers"]["console"]["formatter"], "json")
        # The formatter itself must produce one-line JSON records.
        from config.json_logging import JsonLogFormatter

        import logging

        record = logging.LogRecord(
            "payments", logging.INFO, __file__, 1, "سفارش CG-1 پرداخت شد", None, None
        )
        line = JsonLogFormatter().format(record)
        import json as jsonlib

        payload = jsonlib.loads(line)  # raises if not valid single-line JSON
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "payments")
        self.assertIn("CG-1", payload["message"])

    def test_invalid_log_format_fails_loudly(self):
        with self.assertRaises(RuntimeError):
            _import_modules({**VALID_ENV, "LOG_FORMAT": "yaml"})


class SentryInitializationTests(TestCase):
    def setUp(self):
        base = importlib.import_module("config.settings.base")
        self.addCleanup(importlib.reload, base)

    def test_no_dsn_means_no_initialization(self):
        env = dict(VALID_ENV)
        env.pop("SENTRY_DSN", None)
        with mock.patch("sentry_sdk.init") as init:
            _import_modules(env)
        init.assert_not_called()

    def test_dsn_initializes_with_env_settings(self):
        env = {
            **VALID_ENV,
            "SENTRY_DSN": "https://examplePublicKey@o0.ingest.sentry.io/0",
            "SENTRY_ENVIRONMENT": "staging",
            "SENTRY_TRACES_SAMPLE_RATE": "0.25",
        }
        with mock.patch("sentry_sdk.init") as init:
            _import_modules(env)
        init.assert_called_once()
        kwargs = init.call_args.kwargs
        self.assertEqual(kwargs["dsn"], env["SENTRY_DSN"])
        self.assertEqual(kwargs["environment"], "staging")
        self.assertEqual(kwargs["traces_sample_rate"], 0.25)
