"""
Shipping cost calculation (Phase 6).

The one place shipping cost is computed -- checkout/order code calls
calculate_shipping_cost() and nothing else ever hardcodes a shipping
number or threshold, per master spec section 34: "Create a shipping
system abstraction... do not hardcode shipping logic throughout the
code."

Deliberately a single flat rate + free-shipping threshold for now, not a
multi-carrier/multi-method system -- nothing in the master spec asks for
selectable carriers, and building one speculatively would be exactly the
over-engineering this project has consistently avoided. The function
signature (subtotal in, cost out) is intentionally the only thing
checkout code depends on: swapping the internals for a real
carrier/weight/zone-based system later requires changing only this
module, not the checkout flow or serializers that call it.
"""
from django.conf import settings

STANDARD_METHOD = "standard"


def calculate_shipping_cost(subtotal: int) -> int:
    """
    Whole-Toman flat rate, free above FREE_SHIPPING_THRESHOLD. Both
    values are configured via environment variables (see
    config/settings/base.py's "Shipping (Phase 6)" section), not magic
    numbers here.
    """
    if subtotal >= settings.FREE_SHIPPING_THRESHOLD:
        return 0
    return settings.STANDARD_SHIPPING_COST


def get_shipping_method_name() -> str:
    """
    Returns the identifier for the (currently single) shipping method
    checkout uses -- exposed as its own function rather than a bare
    string constant referenced directly, so callers have one place to
    ask "what method is this" that can later return one of several
    options without changing their code.
    """
    return STANDARD_METHOD
