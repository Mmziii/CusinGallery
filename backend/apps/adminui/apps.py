from django.apps import AppConfig


class AdminuiConfig(AppConfig):
    """Admin panel tooling: theme helpers, Jalali display filter, dashboard
    payload, quick-search endpoint and staff-group command.

    Model-less on purpose -- nothing here owns database state, so the whole
    feature can be switched off (ADMIN_THEME_ENABLED=False) or removed
    without migrations.
    """

    name = "apps.adminui"
    verbose_name = "ابزارهای پنل مدیریت"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Persian titles for the django-otp admins (see third_party_admin.py).
        # Runs after django.contrib.admin's autodiscover, which registers them.
        from .admin_actions import install_persian_admin_actions
        from .jalali_forms import install_jalali_admin_fields
        from .third_party_admin import register_persian_otp_admins

        install_jalali_admin_fields()
        register_persian_otp_admins()
        install_persian_admin_actions()
