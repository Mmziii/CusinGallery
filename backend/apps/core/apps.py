from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "امکانات پایه و تنظیمات سایت"

    def ready(self):
        # Cache invalidation for the public site-content payload (content,
        # trust strip, info pages). Imported for its signal receivers.
        from . import signals  # noqa: F401
