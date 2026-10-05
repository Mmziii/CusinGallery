"""
Recovery command (Part R4 item 4): wipe a user's two-factor devices so
they can re-enroll with manage.py enroll_admin_2fa.

    python manage.py reset_admin_2fa <username-or-phone>

Use when a staff member lost their authenticator device AND their backup
codes. Until they re-enroll, they cannot log into the admin while
ADMIN_2FA_REQUIRED is on -- which is exactly the point of the gate.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Recovery: remove all two-factor devices of a user so they can re-enroll."

    def add_arguments(self, parser):
        parser.add_argument("identifier", help="username or phone of the staff user")

    def handle(self, *args, **options):
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice

        User = get_user_model()
        user = None
        for lookup in ({"username": options["identifier"]}, {"phone": options["identifier"]}):
            user = User.objects.filter(**lookup).first()
            if user is not None:
                break
        if user is None:
            raise CommandError(f"کاربری با این شناسه پیدا نشد: {options['identifier']}")

        totp_count = TOTPDevice.objects.filter(user=user).delete()[0]
        static_count = StaticDevice.objects.filter(user=user).delete()[0]
        self.stdout.write(self.style.SUCCESS(
            f"دستگاه‌های تائید دومرحله‌ای {user.username} حذف شد "
            f"({totp_count + static_count} ردیف). با enroll_admin_2fa دوباره ثبت‌نام کنید."
        ))
