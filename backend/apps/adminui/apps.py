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
