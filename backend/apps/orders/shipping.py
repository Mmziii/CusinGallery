"""
Shipping calculation (Phase 6; selectable methods + delivery windows
added in the Phase A corrections round).

The one place shipping cost and delivery estimates are computed --
checkout/order code calls calculate_shipping_cost() /
calculate_estimated_delivery() and nothing else ever hardcodes a
shipping number, threshold, or delivery window, per master spec section
34: "Create a shipping system abstraction... do not hardcode shipping
logic throughout the code."

Selectable methods (default: "standard" and "express") and all of their
costs/delivery windows come from settings.SHIPPING_METHODS (built from
env vars in config/settings/base.py). Orders SNAPSHOT the chosen method,
its cost, and its delivery window at checkout time (see
apps.orders.models.Order) -- a later settings change never rewrites an
existing order.
"""
import datetime

from django.conf import settings
from django.utils import timezone

DEFAULT_METHOD = "standard"


def get_shipping_methods() -> dict:
    """
    The currently configured methods, keyed by identifier, each with
    `cost`, `free_threshold` (None = never free) and `min_days`/`max_days`
    delivery window. Reads settings at call time (not import time) so
    tests can override_settings() freely.
    """
    return settings.SHIPPING_METHODS


def is_valid_shipping_method(method) -> bool:
    return method in get_shipping_methods()


def _method_config(method: str) -> dict:
    methods = get_shipping_methods()
    if method not in methods:
        raise ValueError(
            f"Unknown shipping method '{method}'. "
            f"Configured methods: {', '.join(methods)}."
        )
    return methods[method]


def calculate_shipping_cost(subtotal: int, method: str = DEFAULT_METHOD) -> int:
    """
    Whole-Toman shipping cost for a cart subtotal using the given method.

    Standard behavior is unchanged from Phase 6: a flat rate, free at or
    above the method's free-shipping threshold. Express has no free
    threshold by configuration (its `free_threshold` is None), so its
    fixed cost always applies -- the free-shipping promotion is a
    standard-delivery feature, not a carrier-independent one.
    """
    config = _method_config(method)
    free_threshold = config.get("free_threshold")
    if free_threshold is not None and subtotal >= free_threshold:
        return 0
    return config["cost"]


def calculate_estimated_delivery(
    method: str, from_date: datetime.date | None = None
) -> tuple[datetime.date, datetime.date]:
    """
    Estimated delivery window (inclusive, calendar days) for a method,
    counted from `from_date` (defaults to today). Returns (min_date,
    max_date). Pure computation -- checkout snapshots the result onto
    the Order so it never drifts if settings change later.
    """
    config = _method_config(method)
    start = from_date or timezone.localdate()
    return (
        start + datetime.timedelta(days=config["min_days"]),
        start + datetime.timedelta(days=config["max_days"]),
    )
