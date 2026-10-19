from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """Storefront behaviour events + the owner's «گزارش‌ها و تحلیل» page.

    Privacy model (documented in apps/analytics/models.py): only an
    anonymous random session key is kept -- never an IP address and never
    a user agent. Raw events are pruned after ANALYTICS_RETENTION_DAYS by
    ``manage.py prune_analytics_events`` (see docker-compose.prod.yml's
    scheduler service).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    verbose_name = "گزارش‌ها و تحلیل"
