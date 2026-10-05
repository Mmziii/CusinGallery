"""
Admin two-factor gate (Part R4 item 4).

When settings.ADMIN_2FA_REQUIRED is on, the Django admin site becomes a
django-otp OTPAdminSite: the admin login then requires username +
password + a one-time code from a verified TOTP device (or one of the
one-time backup codes). Customers and the storefront API are completely
unaffected -- this only changes the staff-only admin entry.

The switch is a class swap on the SINGLE global admin.site instance,
which is the django-otp-documented way to protect the built-in admin
without re-registering every ModelAdmin against a custom site.

Lock-out is handled operationally, exactly as the spec asks:
  * manage.py enroll_admin_2fa <user>   -- set up a device (prints the
    otpauth URL, a QR PNG path, and one-time backup codes);
  * manage.py reset_admin_2fa <user>   -- recovery: wipe the user's
    devices so they can re-enroll.
"""
from django.conf import settings
from django.contrib import admin


def configure_admin_2fa() -> None:
    """Swap the admin site class according to the current flag. Called
    from config.urls (import time) and from tests."""
    from django.contrib.admin import AdminSite

    if getattr(settings, "ADMIN_2FA_REQUIRED", False):
        from django_otp.admin import OTPAdminSite

        admin.site.__class__ = OTPAdminSite
    else:
        admin.site.__class__ = AdminSite
