"""
Coupon business logic (built on the Phase 2 schema).

One mechanism for everything coupon-related, used by both checkout
(apps.orders.services) and the validate endpoint (views.py): no pricing
or discount arithmetic exists anywhere else in the codebase, per the
same "single mechanism, never duplicated" rule apps/products/pricing.py
established for prices.

Trust model: the client supplies ONLY a coupon code. Everything else --
whether it's active/in-date/within limits, which cart lines it applies
to, and how many Toman it takes off -- is computed here from the
database. There is no field anywhere in the API for a client to send a
discount amount.

Usage-limit enforcement happens at two points, deliberately:
    - checkout: validated under a row lock on the Coupon so two
      concurrent checkouts can't both pass the last remaining use;
    - payment success: the CouponUsage row is written then (see
      apps.payments.services._record_coupon_usage), so abandoned unpaid
      orders never consume quota.
"""
from dataclasses import dataclass

from django.utils import timezone

from apps.categories.models import Category

from .models import Coupon, CouponUsage


class CouponError(Exception):
    """
    Raised for any coupon business-rule violation. Carries a dict shaped
    like a DRF serializer error (field -> [messages]), same convention as
    the other apps' service errors.
    """

    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


@dataclass(frozen=True)
class CouponEvaluation:
    """The full, server-computed result of applying a coupon to a cart."""

    coupon: Coupon
    eligible_subtotal: int
    discount_amount: int


def validate_and_calculate(user, code: str, cart_view: dict) -> CouponEvaluation:
    """
    Validates `code` against the live cart (a build_cart_view() result)
    for `user` and returns the exact Toman discount. Raises CouponError
    with a customer-showable message for any rule violation.

    Only AVAILABLE lines are considered -- an unavailable line is already
    excluded from the cart's subtotal (see apps.cart.services), and a
    coupon must never resurrect value for something that can't be sold.
    """
    if not code or not code.strip():
        raise CouponError({"coupon_code": ["Enter a coupon code."]})

    coupon = _find_active_coupon(code)
    _validate_time_window(coupon)
    _validate_usage_limits(coupon, user)

    available_lines = [line for line in cart_view["lines"] if line.is_available]
    if not available_lines:
        raise CouponError({"coupon_code": ["Your cart has no available items."]})

    eligible_subtotal = _eligible_subtotal(coupon, available_lines)

    if coupon.minimum_order_amount is not None and eligible_subtotal < coupon.minimum_order_amount:
        raise CouponError(
            {
                "coupon_code": [
                    f"This coupon requires a minimum order of {coupon.minimum_order_amount} Toman "
                    "for eligible items."
                ]
            }
        )

    if eligible_subtotal <= 0:
        raise CouponError({"coupon_code": ["This coupon does not apply to your cart items."]})

    discount_amount = _calculate_discount(coupon, eligible_subtotal)
    return CouponEvaluation(
        coupon=coupon, eligible_subtotal=eligible_subtotal, discount_amount=discount_amount
    )


def usage_within_limits(coupon: Coupon, user) -> bool:
    """
    Shared limit check used both at checkout and as the defensive
    re-validation at payment time (see apps.payments.services).
    """
    if coupon.usage_limit is not None:
        if CouponUsage.objects.filter(coupon=coupon).count() >= coupon.usage_limit:
            return False
    if coupon.per_user_usage_limit is not None and user is not None:
        if CouponUsage.objects.filter(coupon=coupon, user=user).count() >= coupon.per_user_usage_limit:
            return False
    return True


# --- Internals ---------------------------------------------------------------


def _find_active_coupon(code: str) -> Coupon:
    """
    Case-insensitive, whitespace-tolerant lookup. Inactive coupons are
    rejected HERE (not left to callers) so every entry point gets the
    same rule.
    """
    try:
        coupon = Coupon.objects.get(code__iexact=code.strip())
    except Coupon.DoesNotExist:
        raise CouponError({"coupon_code": ["This coupon code is not valid."]})

    if not coupon.is_active:
        # Same generic wording as an unknown code -- no reason to tell a
        # client the difference between "disabled" and "never existed".
        raise CouponError({"coupon_code": ["This coupon code is not valid."]})
    return coupon


def _validate_time_window(coupon: Coupon) -> None:
    now = timezone.now()
    if coupon.start_date is not None and now < coupon.start_date:
        raise CouponError({"coupon_code": ["This coupon is not active yet."]})
    if coupon.expiration_date is not None and now > coupon.expiration_date:
        raise CouponError({"coupon_code": ["This coupon has expired."]})


def _validate_usage_limits(coupon: Coupon, user) -> None:
    if not usage_within_limits(coupon, user):
        raise CouponError({"coupon_code": ["This coupon can no longer be used."]})


def _applicable_category_ids(coupon: Coupon) -> set:
    """
    The coupon's targeted categories EXPANDED to include descendants: an
    admin who targets "Cookware" expects a product living in
    "Cookware > Non-stick" to qualify. Categories are a shallow
    adjacency-list tree (see apps.categories), so a bounded BFS is cheap.
    """
    root_ids = set(coupon.applicable_categories.values_list("id", flat=True))
    if not root_ids:
        return set()

    all_ids = set(root_ids)
    frontier = list(root_ids)
    while frontier:
        frontier = list(
            Category.objects.filter(parent_id__in=frontier, is_active=True).values_list("id", flat=True)
        )
        new_ids = set(frontier) - all_ids
        all_ids |= new_ids
        frontier = list(new_ids)
    return all_ids


def _eligible_subtotal(coupon: Coupon, available_lines) -> int:
    """
    The Toman base the discount is computed from. A coupon with no
    product/category targeting applies to the whole available cart; a
    targeted coupon only to the matching lines.
    """
    product_ids = set(coupon.applicable_products.values_list("id", flat=True))
    category_ids = _applicable_category_ids(coupon)
    if not product_ids and not category_ids:
        return sum(line.line_total for line in available_lines)

    total = 0
    for line in available_lines:
        product_id = line.item.product_id
        category_id = line.item.product.category_id
        if product_id in product_ids or category_id in category_ids:
            total += line.line_total
    return total


def _calculate_discount(coupon: Coupon, eligible_subtotal: int) -> int:
    """
    Whole-Toman discount, never exceeding the eligible subtotal (a coupon
    can't make a cart negative, and a fixed coupon larger than the
    eligible items simply covers those items).
    """
    if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
        discount = (eligible_subtotal * coupon.percentage_value) // 100
        if coupon.maximum_discount_amount is not None:
            discount = min(discount, coupon.maximum_discount_amount)
    else:  # FIXED
        discount = coupon.fixed_value or 0

    return min(discount, eligible_subtotal)
