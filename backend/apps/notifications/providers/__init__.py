"""
SMS provider registry (Phase D - Notifications).

`get_provider()` returns the configured SMS provider, selected by
settings.SMS_PROVIDER (read from the SMS_PROVIDER env var). An empty
value or "console" selects the development-only ConsoleSMSProvider,
which logs instead of sending; config/settings/production.py refuses to
boot with it while SMS features are enabled -- the exact same pattern as
apps/payments/gateways for the mock gateway.

Adding another provider (Melipayamak, SMS.ir, ...) is: write an
SMSProvider subclass in this package, add ONE entry to _REGISTRY below,
document its env variables. Services and callers never change.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import SMSProvider, SMSProviderError
from .console import ConsoleSMSProvider
from .kavenegar import KavenegarProvider

_REGISTRY = {
    ConsoleSMSProvider.name: ConsoleSMSProvider,
    KavenegarProvider.name: KavenegarProvider,
}


def get_provider() -> SMSProvider:
    from django.conf import settings

    name = (getattr(settings, "SMS_PROVIDER", "") or "console").strip().lower()
    if name not in _REGISTRY:
        raise ImproperlyConfigured(
            f"Unknown SMS_PROVIDER '{name}'. Available: {', '.join(sorted(_REGISTRY))}. "
            "Add an SMSProvider subclass to apps/notifications/providers/ and register it."
        )
    return _REGISTRY[name]()


__all__ = [
    "SMSProvider",
    "SMSProviderError",
    "ConsoleSMSProvider",
    "KavenegarProvider",
    "get_provider",
]
