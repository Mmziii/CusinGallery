"""
check_production command tests (Phase E).

The command audits the ENVIRONMENT, so tests patch os.environ with a
known-good production set and then break exactly one variable at a time,
asserting the report's PASS/WARN/FAIL lines and the exit code. The
command's final check (re-)imports config/settings/production.py, so the
same module-restore cleanup as the other settings tests applies.
"""
import importlib
import sys
from io import StringIO
from unittest import TestCase, mock

from django.core.management import call_command

VALID_ENV = {
    "SECRET_KEY": "a-real-production-secret-key-value",
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "ALLOWED_HOSTS": "cusin.ir,www.cusin.ir",
    "CSRF_TRUSTED_ORIGINS": "https://cusin.ir,https://www.cusin.ir",
    "CORS_ALLOWED_ORIGINS": "https://cusin.ir,https://www.cusin.ir",
    "POSTGRES_DB": "cusin_gallery",
    "POSTGRES_USER": "cusin_user",
    "POSTGRES_PASSWORD": "a-real-db-password",
    "POSTGRES_HOST": "db",
    "REDIS_URL": "redis://redis:6379/1",
    "PAYMENT_GATEWAY": "zarinpal",
    "PAYMENT_MERCHANT_ID": "c64a6c77-0000-4000-8000-000000000000",
    "PAYMENT_ZARINPAL_SANDBOX": "False",
    "PAYMENT_CALLBACK_URL": "https://cusin.ir/payment/callback/",
    "SMS_PROVIDER": "kavenegar",
    "KAVENEGAR_API_KEY": "a-real-kavenegar-key",
    "EMAIL_HOST": "smtp.example.com",
    "HTTPS_ENABLED": "True",
    "FRONTEND_URL": "https://cusin.ir",
    "SENTRY_DSN": "https://examplePublicKey@o0.ingest.sentry.io/0",
}


class CheckProductionCommandTests(TestCase):
    def setUp(self):
        base = importlib.import_module("config.settings.base")
        self.addCleanup(importlib.reload, base)
        self.addCleanup(sys.modules.pop, "config.settings.production", None)

    def run_command(self, **env_overrides):
        env = dict(VALID_ENV)
        env.update(env_overrides)
        out = StringIO()
        exit_code = 0
        with mock.patch.dict("os.environ", env, clear=True):
            try:
                call_command("check_production", stdout=out)
            except SystemExit as exc:  # the command's FAIL path
                exit_code = exc.code
        return out.getvalue(), exit_code

    def test_a_valid_environment_passes_with_exit_zero(self):
        output, code = self.run_command()
        self.assertEqual(code, 0, output)
        self.assertNotIn("[FAIL]", output)
        self.assertIn("[PASS]", output)
        self.assertIn("0 failed", output)
        # The bilingual summary is part of the contract.
        self.assertIn("RESULT:", output)
        self.assertIn("آماده", output)

    def test_missing_secret_key_fails(self):
        output, code = self.run_command(SECRET_KEY="")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] SECRET_KEY", output)

    def test_development_default_secret_key_fails(self):
        output, code = self.run_command(
            SECRET_KEY="unsafe-development-secret-key-do-not-use-in-production"
        )
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] SECRET_KEY", output)

    def test_placeholder_database_password_fails(self):
        output, code = self.run_command(POSTGRES_PASSWORD="change-me-before-deploying")
        self.assertEqual(code, 1)
        self.assertIn("POSTGRES_PASSWORD", output)

    def test_sqlite_database_url_fails(self):
        output, code = self.run_command(DATABASE_URL="sqlite:///db.sqlite3")
        self.assertEqual(code, 1)
        self.assertIn("SQLite", output)

    def test_empty_cors_fails(self):
        output, code = self.run_command(CORS_ALLOWED_ORIGINS="")
        self.assertEqual(code, 1)
        self.assertIn("CORS_ALLOWED_ORIGINS", output)

    def test_wildcard_allowed_hosts_fails(self):
        output, code = self.run_command(ALLOWED_HOSTS="*")
        self.assertEqual(code, 1)
        self.assertIn("'*'", output)

    def test_mock_payment_gateway_fails(self):
        output, code = self.run_command(PAYMENT_GATEWAY="mock")
        self.assertEqual(code, 1)
        self.assertIn("PAYMENT_GATEWAY", output)

    def test_zarinpal_without_merchant_id_fails(self):
        output, code = self.run_command(PAYMENT_MERCHANT_ID="")
        self.assertEqual(code, 1)
        self.assertIn("PAYMENT_MERCHANT_ID", output)

    def test_sandbox_mode_warns_loudly_but_is_not_a_failure(self):
        """Sandbox-on is the pre-launch rehearsal state: the report must
        scream about it, but it must not block a rehearsal deploy."""
        output, code = self.run_command(PAYMENT_ZARINPAL_SANDBOX="True")
        self.assertEqual(code, 0, output)
        self.assertIn("[WARN]", output)
        self.assertIn("NO REAL MONEY", output)

    def test_console_sms_provider_fails_while_sms_enabled(self):
        output, code = self.run_command(SMS_PROVIDER="console")
        self.assertEqual(code, 1)
        self.assertIn("SMS_PROVIDER", output)

    def test_kavenegar_without_key_fails(self):
        output, code = self.run_command(KAVENEGAR_API_KEY="")
        self.assertEqual(code, 1)
        self.assertIn("KAVENEGAR_API_KEY", output)

    def test_explicit_sms_disabled_is_accepted(self):
        output, code = self.run_command(SMS_ENABLED="False", SMS_PROVIDER="console")
        self.assertEqual(code, 0, output)
        self.assertNotIn("[FAIL]", output)
        self.assertIn("opt-out", output)

    def test_https_disabled_warns(self):
        output, code = self.run_command(HTTPS_ENABLED="False")
        self.assertEqual(code, 0)
        self.assertIn("HTTPS_ENABLED=False", output)

    def test_missing_email_host_warns(self):
        output, code = self.run_command(EMAIL_HOST="")
        self.assertEqual(code, 0)
        self.assertIn("EMAIL_HOST", output)

    def test_missing_sentry_warns_but_does_not_fail(self):
        output, code = self.run_command(SENTRY_DSN="")
        self.assertEqual(code, 0)
        self.assertIn("SENTRY_DSN", output)

    def test_production_boot_guard_is_part_of_the_report(self):
        """The command's last line proves the production module itself
        would actually import with this environment -- break a boot guard
        and BOTH the specific check and the boot check must flag it."""
        output, code = self.run_command(CORS_ALLOWED_ORIGINS="")
        self.assertEqual(code, 1)
        self.assertIn("REFUSES to boot", output)

    def test_http_callback_url_warns(self):
        output, code = self.run_command(PAYMENT_CALLBACK_URL="http://cusin.ir/payment/callback/")
        self.assertEqual(code, 0)
        self.assertIn("not HTTPS", output)
