"""
Production gateway-configuration guard tests (Phase C - Real payments).

The MockGateway must be IMPOSSIBLE to enable in production. That rule
lives in config/settings/production.py as a boot-time RuntimeError, so
these tests exercise the real settings module: they reload it (and the
base module it reads env through) under a patched environment and assert
it refuses or accepts exactly as documented.

Reloading settings modules is unusual, hence the careful cleanup: the
base module is reloaded again OUTSIDE the patched env afterwards so the
rest of the test suite keeps seeing the real test environment, and the
production module (which no other code imports at runtime -- Django runs
on config.settings.development here) is dropped from sys.modules.
"""
import importlib
import os
import sys
from unittest import TestCase, mock

# A production environment that is valid in every other respect, so the
# ONLY thing under test is the payment-gateway guard.
VALID_PRODUCTION_ENV = {
    "SECRET_KEY": "production-guard-test-key-not-the-dev-default",
    "CORS_ALLOWED_ORIGINS": "https://cusin.ir",
    "ALLOWED_HOSTS": "cusin.ir",
    "PAYMENT_GATEWAY": "zarinpal",
    "PAYMENT_MERCHANT_ID": "c64a6c77-0000-4000-8000-000000000000",
    "PAYMENT_CALLBACK_URL": "https://cusin.ir/payment/callback/",
}


class ProductionGatewayGuardTests(TestCase):
    """Plain TestCase (not Django's): these tests never touch the DB, the
    test client, or django.conf.settings -- they only import modules."""

    def _import_production(self, **env_overrides):
        env = dict(VALID_PRODUCTION_ENV)
        env.update(env_overrides)
        # Everything happens INSIDE the patched environment: production.py
        # executes its guards at import time, so even the first import of
        # the module must see the intended env. import_module is a no-op
        # when the module is cached; the reload guarantees the body
        # re-executes under the patch either way.
        with mock.patch.dict(os.environ, env):
            base = importlib.import_module("config.settings.base")
            importlib.reload(base)
            production = importlib.import_module("config.settings.production")
            importlib.reload(production)
        return production

    def setUp(self):
        # Never leak patched settings state into other tests.
        base = importlib.import_module("config.settings.base")
        self.addCleanup(importlib.reload, base)
        self.addCleanup(sys.modules.pop, "config.settings.production", None)

    def test_production_refuses_the_mock_gateway(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._import_production(PAYMENT_GATEWAY="mock")
        message = str(ctx.exception)
        self.assertIn("mock", message)
        self.assertIn("production", message.lower())

    def test_production_refuses_an_empty_gateway_meaning_mock(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._import_production(PAYMENT_GATEWAY="")
        self.assertIn("mock", str(ctx.exception))

    def test_production_refuses_zarinpal_without_a_merchant_id(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._import_production(PAYMENT_MERCHANT_ID="")
        self.assertIn("PAYMENT_MERCHANT_ID", str(ctx.exception))

    def test_production_accepts_zarinpal_with_a_merchant_id(self):
        production = self._import_production()
        self.assertEqual(production.PAYMENT_GATEWAY, "zarinpal")
        self.assertEqual(production.PAYMENT_MERCHANT_ID, VALID_PRODUCTION_ENV["PAYMENT_MERCHANT_ID"])

    def test_production_accepts_zarinpal_sandbox_for_pre_launch_testing(self):
        """Sandbox mode is a legitimate production-settings configuration:
        it is how the owner tests the real gateway flow on the real
        deployment before switching PAYMENT_ZARINPAL_SANDBOX to False."""
        production = self._import_production(PAYMENT_ZARINPAL_SANDBOX="True")
        self.assertTrue(production.PAYMENT_ZARINPAL_SANDBOX)
