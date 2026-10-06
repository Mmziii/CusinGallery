"""
Gateway registry (Phase 7 - Payment architecture; Phase C - real payments).

`get_gateway()` returns the configured gateway implementation, selected
by settings.PAYMENT_GATEWAY (read from the PAYMENT_GATEWAY env var):

    PAYMENT_GATEWAY=mock       the self-contained MockGateway --
                               development and tests ONLY.
                               config/settings/production.py refuses to
                               start with it (or with an empty value,
                               which means the same thing), so it is
                               impossible to enable in production.
    PAYMENT_GATEWAY=zarinpal   the real ZarinPal PSP adapter
                               (gateways/zarinpal.py), which also covers
                               pre-launch testing through ZarinPal's own
                               sandbox mode (PAYMENT_ZARINPAL_SANDBOX).

Adding another gateway is: write a PaymentGateway subclass in this
package, add ONE entry to _REGISTRY below, document its env variables.
Services, views, admin and the frontend need no changes -- they only
ever see the base.py interface.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import (
    GatewayError,
    InitiateResult,
    PaymentGateway,
    VerificationResult,
)
from .mock import MockGateway
from .zarinpal import ZarinpalGateway

_REGISTRY = {
    MockGateway.name: MockGateway,
    ZarinpalGateway.name: ZarinpalGateway,
}


def get_gateway() -> PaymentGateway:
    from django.conf import settings

    name = (getattr(settings, "PAYMENT_GATEWAY", "") or "mock").strip().lower()
    if name not in _REGISTRY:
        raise ImproperlyConfigured(
            f"Unknown PAYMENT_GATEWAY '{name}'. Available: {', '.join(sorted(_REGISTRY))}. "
            "Add a PaymentGateway subclass to apps/payments/gateways/ and register it."
        )
    return _REGISTRY[name]()


__all__ = [
    "GatewayError",
    "InitiateResult",
    "PaymentGateway",
    "VerificationResult",
    "MockGateway",
    "ZarinpalGateway",
    "get_gateway",
]
