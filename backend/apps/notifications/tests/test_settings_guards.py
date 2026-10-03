"""
Production SMS-configuration guard tests (Phase D).

Same technique as apps/payments/tests/test_gateway_config.py: the guard
lives in config/settings/production.py and fires at BOOT, so the tests
reload the real settings modules under a patched environment and assert
it refuses or accepts exactly as documented:

  * SMS_ENABLED=True (the default) + console/empty provider -> refuse
    (the console provider is a dev/test logging tool, like the mock
    payment gateway);
  * kavenegar without KAVENEGAR_API_KEY -> refuse;
  * kavenegar with a key -> accept;
  * SMS_ENABLED=False + console -> accept (explicit, honest opt-out of
    SMS; phone-only resets then log a SKIPPED notification).
"""
import importlib
import os
import sys
from unittest import TestCase, mock

VALID_PRODUCTION_ENV = {
    "SECRET_KEY": "production-guard-test-key-not-the-dev-default",
    "CORS_ALLOWED_ORIGINS": "https://cusin.ir",
    "ALLOWED_HOSTS": "cusin.ir",
    "PAYMENT_GATEWAY": "zarinpal",
    "PAYMENT_MERCHANT_ID": "c64a6c77-0000-4000-8000-000000000000",
    "SMS_PROVIDER": "kavenegar",
    "KAVENEGAR_API_KEY": "production-guard-test-kavenegar-key",
    "SMS_ENABLED": "True",
}


class ProductionSMSGuardTests(TestCase):
    """Plain TestCase: no DB, no test client, no django.conf.settings --
    only module imports under a patched environment."""

    def _import_production(self, **env_overrides):
        env = dict(VALID_PRODUCTION_ENV)
        env.update(env_overrides)
        # Everything happens INSIDE the patched environment: production.py
        # executes its guards at import time. import_module is a no-op when
        # cached; the reloads guarantee both modules re-execute under it.
        with mock.patch.dict(os.environ, env):
            base = importlib.import_module("config.settings.base")
            importlib.reload(base)
            production = importlib.import_module("config.settings.production")
            importlib.reload(production)
        return production

    def setUp(self):
        base = importlib.import_module("config.settings.base")
        self.addCleanup(importlib.reload, base)
        self.addCleanup(sys.modules.pop, "config.settings.production", None)

    def test_production_refuses_the_console_sms_provider(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._import_production(SMS_PROVIDER="console")
        message = str(ctx.exception)
        self.assertIn("console", message)
        self.assertIn("SMS_PROVIDER", message)

    def test_production_refuses_an_empty_sms_provider_meaning_console(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._import_production(SMS_PROVIDER="")
        self.assertIn("console", str(ctx.exception))

    def test_production_refuses_kavenegar_without_an_api_key(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._import_production(KAVENEGAR_API_KEY="")
        self.assertIn("KAVENEGAR_API_KEY", str(ctx.exception))

    def test_production_accepts_kavenegar_with_an_api_key(self):
        production = self._import_production()
        self.assertEqual(production.SMS_PROVIDER, "kavenegar")
        self.assertTrue(production.SMS_ENABLED)

    def test_production_accepts_explicit_sms_disabled_with_console(self):
        """The honest opt-out: no SMS features at all. Phone-only password
        resets then record a SKIPPED NotificationLog instead of pretending."""
        production = self._import_production(SMS_ENABLED="False", SMS_PROVIDER="console")
        self.assertFalse(production.SMS_ENABLED)
