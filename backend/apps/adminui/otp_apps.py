"""Persian display names for the django-otp plugin apps.

The plugins ship AppConfigs without a verbose_name, so the admin showed their
labels in English. These subclasses keep the plugin's name and label (no
migration or model state changes) and add only the Persian verbose_name.
config/settings/base.py registers them in INSTALLED_APPS in place of the
plugin paths. They live in their own module so apps/adminui/apps.py keeps a
single AppConfig for Django to detect.
"""
from django_otp.plugins.otp_static.apps import DefaultConfig as _OtpStaticDefaultConfig
from django_otp.plugins.otp_totp.apps import DefaultConfig as _OtpTotpDefaultConfig


class OtpStaticAdminConfig(_OtpStaticDefaultConfig):
    verbose_name = "کدهای پشتیبان ورود دومرحله‌ای"


class OtpTotpAdminConfig(_OtpTotpDefaultConfig):
    verbose_name = "کد یک‌بارمصرف مبتنی بر زمان"
