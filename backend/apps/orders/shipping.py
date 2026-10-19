"""
Shipping calculation (Phase 6; selectable methods + delivery windows
added in the Phase A corrections round).

The one place shipping cost and delivery estimates are computed --
checkout/order code calls calculate_shipping_cost() /
calculate_estimated_delivery() and nothing else ever hardcodes a
shipping number, threshold, or delivery window, per master spec section
34: "Create a shipping system abstraction... do not hardcode shipping
logic throughout the code."

Selectable methods (default: "standard" and "express") and their
costs/delivery windows are managed in the admin under «محتوا و ظاهر سایت»
(SiteSettings). Orders SNAPSHOT the chosen method, its cost, and its
delivery window at checkout time (see apps.orders.models.Order) -- a
later settings change never rewrites an existing order.
"""
import datetime
import re

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

DEFAULT_METHOD = "standard"
EXPRESS_UNAVAILABLE_MESSAGE = "ارسال اکسپرس فعلاً فقط برای شهر تهران"
SHIPPING_METHODS_CACHE_KEY = "orders:shipping_methods:v1"


def invalidate_shipping_cache() -> None:
    cache.delete(SHIPPING_METHODS_CACHE_KEY)


def get_express_allowed_cities() -> set[str]:
    """Retrieve the set of cities eligible for express delivery from SiteSettings."""
    try:
        from apps.core.models import SiteSettings

        site = SiteSettings.load()
        raw = getattr(site, "shipping_express_cities", "") or "تهران"
    except Exception:
        raw = "تهران"

    from apps.accounts.locations import normalize_city

    cities = set()
    for item in re.split(r"[\n,،;؛]+", raw):
        cleaned = item.strip()
        if not cleaned:
            continue
        norm = normalize_city(cleaned)
        if norm:
            cities.add(norm)
            if norm == "تهران":
                cities.add("شهرستان تهران")
    return cities or {"تهران", "شهرستان تهران"}


def is_express_eligible(province, city) -> bool:
    """Check destination eligibility for express shipping against configured allowed cities.

    Retain support for the official legacy address aliases ("Tehran")
    and the explicit شهرستان تهران spelling; never use substring matches.
    This only compares destinations and never rewrites historical data.
    """
    from apps.accounts.locations import normalize_city, normalize_province, _known_city_map

    province = " ".join((province or "").split())
    city = " ".join((city or "").split())
    norm_city = normalize_city(city)
    norm_prov = normalize_province(province)

    allowed = get_express_allowed_cities()
    if norm_city not in allowed:
        return False

    expected_prov = _known_city_map().get(norm_city)
    if expected_prov:
        return norm_prov == expected_prov
    if norm_city in {"تهران", "شهرستان تهران"}:
        return norm_prov == "تهران"
    return True


def _build_shipping_methods_from_db() -> dict:
    try:
        from apps.core.models import SiteSettings

        site = SiteSettings.load()
    except Exception:
        return getattr(settings, "SHIPPING_METHODS", {})

    methods = {}
    if getattr(site, "shipping_standard_enabled", True):
        methods["standard"] = {
            "label": "عادی",
            "cost": getattr(site, "shipping_standard_cost", getattr(settings, "STANDARD_SHIPPING_COST", 50000)),
            "free_threshold": getattr(site, "shipping_free_threshold", getattr(settings, "FREE_SHIPPING_THRESHOLD", 1000000)),
            "min_days": getattr(site, "shipping_standard_min_days", getattr(settings, "SHIPPING_MIN_DELIVERY_DAYS", 3)),
            "max_days": getattr(site, "shipping_standard_max_days", getattr(settings, "SHIPPING_MAX_DELIVERY_DAYS", 5)),
            "description": getattr(site, "shipping_standard_description", "") or "",
            "requires_address": True,
        }
    if getattr(site, "shipping_express_enabled", True):
        methods["express"] = {
            "label": "اکسپرس",
            "cost": getattr(site, "shipping_express_cost", getattr(settings, "EXPRESS_SHIPPING_COST", 90000)),
            "free_threshold": None,
            "min_days": getattr(site, "shipping_express_min_days", 1),
            "max_days": getattr(site, "shipping_express_max_days", 1),
            "description": getattr(site, "shipping_express_description", "") or "",
            "requires_address": True,
        }
    if getattr(site, "shipping_pickup_enabled", True):
        methods["pickup"] = {
            "label": "حضوری",
            "cost": 0,
            "free_threshold": None,
            "min_days": 0,
            "max_days": 0,
            "description": getattr(site, "shipping_pickup_description", "") or getattr(site, "pickup_hours", "") or "",
            "requires_address": False,
        }
    return methods


def get_shipping_methods() -> dict:
    """
    The currently configured methods, keyed by identifier, each with
    `cost`, `free_threshold` (None = never free) and `min_days`/`max_days`
    delivery window. Reads SiteSettings (cached), while respecting explicit
    override_settings() in tests.
    """
    default_methods = getattr(settings, "DEFAULT_SHIPPING_METHODS", None)
    if default_methods is not None and settings.SHIPPING_METHODS is not default_methods:
        return settings.SHIPPING_METHODS

    cached = cache.get(SHIPPING_METHODS_CACHE_KEY)
    if cached is not None:
        return cached

    methods = _build_shipping_methods_from_db()
    cache.set(SHIPPING_METHODS_CACHE_KEY, methods, 60 * 60 * 24)
    return methods


def is_valid_shipping_method(method) -> bool:
    return method in get_shipping_methods()


def method_label(method: str) -> str:
    """Persian display label for a method key (admin, print, CSV, UI).
    Falls back to the raw key so historical snapshots of removed methods
    never crash a render."""
    return get_shipping_methods().get(method, {}).get("label", method)


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
