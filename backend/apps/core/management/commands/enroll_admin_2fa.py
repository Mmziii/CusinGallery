"""
Enroll a staff/superuser in admin two-factor auth (Part R4 item 4).

    python manage.py enroll_admin_2fa <username-or-phone> [--codes 8]

Creates (or REPLACES) the user's confirmed TOTP device, prints:
  * the otpauth:// URL for the authenticator app,
  * the path of a QR-code PNG encoding that URL,
  * a fresh set of one-time backup codes (each usable exactly once).

This is the deliberate lock-out escape hatch: it runs on the server with
shell access, so an owner who lost their phone can always be re-enrolled
without weakening the admin gate. Recovery (device wipe) is
manage.py reset_admin_2fa.
"""
import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


def _find_user(identifier):
    User = get_user_model()
    for lookup in ({"username": identifier}, {"phone": identifier}):
        user = User.objects.filter(**lookup).first()
        if user is not None:
            return user
    raise CommandError(f"کاربری با این شناسه پیدا نشد: {identifier}")


class Command(BaseCommand):
    help = (
        "Set up (or replace) admin two-factor auth devices for a user: prints the "
        "otpauth URL, a QR PNG path and one-time backup codes."
    )

    def add_arguments(self, parser):
        parser.add_argument("identifier", help="username or phone of the staff user")
        parser.add_argument("--codes", type=int, default=8,
                            help="how many one-time backup codes to print (default 8)")
        parser.add_argument("--qr-path", default="",
                            help="where to write the QR PNG (default: current directory)")

    def handle(self, *args, **options):
        from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
        from django_otp.plugins.otp_totp.models import TOTPDevice

        user = _find_user(options["identifier"])
        if not user.is_staff:
            raise CommandError("این کاربر دسترسی پنل مدیریت ندارد (is_staff نیست).")

        # Replace any previous TOTP device: re-enrollment must win.
        TOTPDevice.objects.filter(user=user).delete()
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)

        otpauth_url = device.config_url
        qr_path = options["qr_path"] or os.getcwd()
        os.makedirs(qr_path, exist_ok=True)
        qr_file = os.path.join(qr_path, f"admin-2fa-{user.username}-qrcode.png")
        import qrcode

        qrcode.make(otpauth_url).save(qr_file)

        # Fresh one-time backup codes (previous ones are invalidated).
        StaticDevice.objects.filter(user=user).delete()
        static = StaticDevice.objects.create(user=user, name="backup", confirmed=True)
        codes = [secrets.choice("23456789") + "".join(
            secrets.choice("0123456789") for _ in range(7)) for _ in range(max(1, options["codes"]))]
        StaticToken.objects.bulk_create(
            [StaticToken(device=static, token=code) for code in codes]
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"دستگاه تائید دومرحله‌ای برای {user.username} ساخته شد."))
        self.stdout.write(f"otpauth URL: {otpauth_url}")
        self.stdout.write(f"QR image   : {qr_file}")
        self.stdout.write("Backup codes (each works exactly once -- store them safely):")
        for code in codes:
            self.stdout.write(f"  {code}")
