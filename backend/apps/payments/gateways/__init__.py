"""
Gateway registry (Phase 7 - Payment architecture).

`get_gateway()` returns the configured gateway implementation, selected
by settings.PAYMENT_GATEWAY (read from the PAYMENT_GATEWAY env var).
An empty value or "mock" selects the self-contained MockGateway, which
needs no credentials -- the correct default while no real PSP has been
chosen (the project forbids inventing credentials). Adding a real
gateway later is: write a PaymentGateway subclass, register it in
_REGISTRY below, set PAYMENT_GATEWAY to its name.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import (
    GatewayError,
    InitiateResult,
    PaymentGateway,
    VerificationResult,
)
from .mock import MockGateway

_REGISTRY = {
    MockGateway.name: MockGateway,
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
    "get_gateway",
]
