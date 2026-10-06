"""
Admin two-factor auth tests (Part R4 item 4).

Real behaviour: the admin site is actually swapped to django-otp's
OTPAdminSite (the same wiring config/urls.py performs at boot), logins
POST the genuine admin login form, TOTP tokens are computed from the
device's real secret, and backup codes come from real StaticDevice rows.
Customers never see any of this -- one test proves the storefront login
is untouched.
"""
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.admin_2fa import configure_admin_2fa

User = get_user_model()

# Admin templates need {% static %}; keep tests independent of a built
# manifest (same reasoning as apps/products/tests/test_admin_products.py).
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


def current_totp(device):
    from django_otp.oath import totp

    return str(totp(device.bin_key, step=device.step, digits=device.digits)).zfill(device.digits)


@override_settings(**PLAIN_STATIC)
class AdminTwoFactorTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="owner2fa", password="a-strong-passw0rd!", phone="+989002223344"
        )

    def enable_2fa(self):
        """Turn the flag on AND apply the same class-swap urls.py does."""
        ctx = override_settings(ADMIN_2FA_REQUIRED=True)
        ctx.enable()
        configure_admin_2fa()

        def restore():
            ctx.disable()          # flag back to False FIRST, then
            configure_admin_2fa()  # restore the plain AdminSite class

        self.addCleanup(restore)

    def login_post(self, **extra):
        payload = {"username": "owner2fa", "password": "a-strong-passw0rd!"}
        payload.update(extra)
        return self.client.post(reverse("admin:login"), payload, follow=False)

    # --- flag off: current behaviour is preserved -------------------------
    def test_flag_off_plain_admin_login_still_works(self):
        from django.conf import settings

        self.assertFalse(settings.ADMIN_2FA_REQUIRED)
        response = self.login_post()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    # --- flag on: staff without a device are locked out --------------------
    def test_flag_on_staff_without_device_cannot_log_in(self):
        self.enable_2fa()
        response = self.login_post()
        self.assertEqual(response.status_code, 200)  # bounced back to login
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_flag_on_staff_with_wrong_token_cannot_log_in(self):
        self.enable_2fa()
        from django_otp.plugins.otp_totp.models import TOTPDevice

        device = TOTPDevice.objects.create(user=self.staff, name="default", confirmed=True)
        response = self.login_post(otp_device=device.persistent_id, otp_token="000000")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    # --- flag on: a valid TOTP code gets in ---------------------------------
    def test_flag_on_valid_totp_logs_in(self):
        self.enable_2fa()
        from django_otp.plugins.otp_totp.models import TOTPDevice

        device = TOTPDevice.objects.create(user=self.staff, name="default", confirmed=True)
        response = self.login_post(
            otp_device=device.persistent_id, otp_token=current_totp(device)
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    # --- flag on: one-time backup code works exactly once -------------------
    def test_flag_on_backup_code_is_single_use(self):
        self.enable_2fa()
        from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

        static = StaticDevice.objects.create(user=self.staff, name="backup", confirmed=True)
        StaticToken.objects.create(device=static, token="11223344")

        response = self.login_post(otp_device=static.persistent_id, otp_token="11223344")
        self.assertEqual(response.status_code, 302)
        self.client.logout()

        response = self.login_post(otp_device=static.persistent_id, otp_token="11223344")
        self.assertEqual(response.status_code, 200)  # the code is spent
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    # --- customers are unaffected -------------------------------------------
    def test_customer_login_unaffected_by_the_flag(self):
        self.enable_2fa()
        customer = User.objects.create_user(
            username="+989125556677", phone="+989125556677", password="a-strong-passw0rd!"
        )
        response = self.client.post(
            "/api/v1/accounts/login/",
            {"identifier": "+989125556677", "password": "a-strong-passw0rd!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("id"), customer.pk)


class EnrollAndResetCommandTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="owner-enroll", password="a-strong-passw0rd!", phone="+989004445566"
        )

    def test_enroll_creates_confirmed_devices_and_recovery_wipes_them(self):
        from io import StringIO

        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice

        out = StringIO()
        with mock.patch.dict(os.environ, {}):
            from django.core.management import call_command

            call_command("enroll_admin_2fa", "owner-enroll", "--qr-path", "/tmp", stdout=out)

        text = out.getvalue()
        self.assertIn("otpauth://totp/", text)
        self.assertIn("QR image", text)
        device = TOTPDevice.objects.get(user=self.staff)
        self.assertTrue(device.confirmed)
        static = StaticDevice.objects.get(user=self.staff)
        self.assertEqual(static.token_set.count(), 8)

        out2 = StringIO()
        from django.core.management import call_command

        call_command("reset_admin_2fa", "owner-enroll", stdout=out2)
        self.assertFalse(TOTPDevice.objects.filter(user=self.staff).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.staff).exists())


class CheckProduction2FATests(TestCase):
    def _run_check(self, env_extra):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with mock.patch.dict(os.environ, env_extra):
            try:
                call_command("check_production", stdout=out)
            except SystemExit:
                pass
        return out.getvalue()

    def test_explicitly_disabled_2fa_fails_the_audit(self):
        output = self._run_check({"ADMIN_2FA_REQUIRED": "False"})
        self.assertIn("ADMIN_2FA_REQUIRED is explicitly disabled", output)

    def test_default_on_passes_that_check(self):
        env = dict(os.environ)
        env.pop("ADMIN_2FA_REQUIRED", None)
        output = self._run_check({})
        self.assertNotIn("ADMIN_2FA_REQUIRED is explicitly disabled", output)
