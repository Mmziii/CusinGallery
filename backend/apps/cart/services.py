"""
Cart business logic (Phase 5).

Kept separate from views.py so the add/update rules -- availability
checking, quantity validation, the increment-not-duplicate behavior --
are testable and reusable independent of the HTTP layer, and so views
stay thin orchestration around these functions.
"""
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.db.models import Prefetch

from apps.products import pricing
from apps.products.models import Product, ProductImage, ProductVariant

from .models import Cart, CartItem


class CartError(Exception):
    """
    Raised for any cart business-rule violation. Carries a dict shaped
    like a DRF serializer error (field -> [messages]) so views can
    translate it directly into a 400 response without re-deriving the
    message.
    """

    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


def get_or_create_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def _resolve_product_and_variant(product_id, variant_id):
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
    except (Product.DoesNotExist, ValueError, TypeError):
        raise CartError({"product": ["This product is unavailable."]})

    variant = None
    if variant_id is not None:
        try:
            variant = ProductVariant.objects.get(pk=variant_id, is_active=True)
        except (ProductVariant.DoesNotExist, ValueError, TypeError):
            raise CartError({"variant": ["This variant is unavailable."]})
        if variant.product_id != product.id:
            raise CartError({"variant": ["This variant does not belong to the selected product."]})

    return product, variant


def _available_stock(product, variant):
    return variant.stock_quantity if variant is not None else product.stock_quantity


def add_item(user, product_id, variant_id, quantity):
    """
    Adds `quantity` of (product, variant) to the user's cart, or
    increments the existing line if one already exists for that exact
    (product, variant) pair -- never creates a duplicate row, matching
    the Phase 2 database constraint this mirrors at the application
    level (see CartItem.Meta.constraints -- the two conditional unique
    constraints for the NULL- vs non-NULL-variant cases).
    """
    if quantity < 1:
        raise CartError({"quantity": ["Quantity must be at least 1."]})

    product, variant = _resolve_product_and_variant(product_id, variant_id)
    # `available` is read here, before the lock below -- deliberately not
    # re-read under a lock on the Product/ProductVariant row itself.
    # Locking the catalog row would serialize every "add to cart" for a
    # popular product across ALL users against each other, for no real
    # benefit: true stock reservation is explicitly deferred to
    # Checkout/Order (master spec step 5/11 -- "do not implement order
    # stock reservation yet"), so this check is a storefront-level
    # sanity check, not a guarantee against overselling across different
    # users' carts. What the locking below DOES guarantee is no lost
    # update for concurrent requests on the SAME user's SAME cart line
    # (e.g. a double-click or two open tabs) -- that's the race this
    # phase is actually responsible for preventing.
    available = _available_stock(product, variant)

    with transaction.atomic():
        cart = get_or_create_cart(user)
        # select_for_update: the read-then-write increment below is a
        # classic lost-update race if two requests for the same line
        # arrive concurrently (e.g. two browser tabs) -- this is the one
        # place in Phase 5 that actually needs row locking, not blanket
        # locking everywhere ("avoid over-engineering... unless
        # justified" -- this specific read-modify-write is the
        # justification).
        existing = (
            CartItem.objects.select_for_update()
            .filter(cart=cart, product=product, variant=variant)
            .first()
        )
        new_quantity = (existing.quantity if existing else 0) + quantity

        if new_quantity > available:
            raise CartError({"quantity": [f"Only {available} available for this item."]})

        if existing:
            existing.quantity = new_quantity
            existing.full_clean()
            existing.save(update_fields=["quantity", "updated_at"])
            return existing

        item = CartItem(cart=cart, product=product, variant=variant, quantity=new_quantity)
        item.full_clean()
        item.save()
        return item


def update_item_quantity(cart_item, quantity):
    """
    Setting quantity to 0 removes the item entirely (per master spec
    step 4: "If quantity reaches zero: remove the item"), signaled to
    the caller by returning None. Removal is always allowed regardless
    of the item's current availability -- there's no reason to block a
    customer from clearing out a now-discontinued line.

    Any positive quantity, by contrast, requires the item to still be
    active: without this check, a product/variant that became inactive
    *after* being added could have its quantity silently increased here,
    even though add_item's _resolve_product_and_variant would correctly
    refuse to add it fresh. Both code paths need to agree that an
    inactive item can only ever go down to zero, never up.
    """
    if quantity < 0:
        raise CartError({"quantity": ["Quantity cannot be negative."]})

    if quantity == 0:
        cart_item.delete()
        return None

    if not cart_item.product.is_active:
        raise CartError(
            {"quantity": ["This product is no longer available. Remove it from your cart."]}
        )
    if cart_item.variant_id and not cart_item.variant.is_active:
        raise CartError(
            {"quantity": ["This variant is no longer available. Remove it from your cart."]}
        )

    available = _available_stock(cart_item.product, cart_item.variant)
    if quantity > available:
        raise CartError({"quantity": [f"Only {available} available for this item."]})

    with transaction.atomic():
        locked = CartItem.objects.select_for_update().get(pk=cart_item.pk)
        locked.quantity = quantity
        locked.full_clean()
        locked.save(update_fields=["quantity", "updated_at"])
    cart_item.refresh_from_db()
    return cart_item


def clear_cart(cart):
    with transaction.atomic():
        cart.items.all().delete()


@dataclass(frozen=True)
class CartLineView:
    item: CartItem
    price_info: "pricing.PriceInfo"
    stock_status: str
    is_available: bool
    unavailable_reason: Optional[str]
    line_total: int


def build_cart_view(cart):
    """
    Computes current pricing/availability for every line in the cart,
    fresh from the catalog every time -- see Cart's own model docstring
    (apps/cart/models.py): "the backend must calculate totals... never
    trust a stored/stale total." Nothing here is cached on the CartItem
    row itself; a repriced or deactivated product is reflected
    immediately on the next GET, no background job required.

    `total` equals `subtotal` for now -- Phase 5 has no shipping cost or
    coupon system wired into the cart yet (coupons are Phase 6, shipping
    is later still). Not a placeholder bug; this is the complete picture
    for what Phase 5 is scoped to calculate. See the README's Cart
    pricing section.

    Unavailable lines (inactive product/variant, or stored quantity now
    exceeding current stock) stay in the response -- never silently
    dropped, so the customer doesn't lose track of what's in their cart
    -- but are excluded from `subtotal`/`total` and flagged via
    `is_available` / `unavailable_reason` so the frontend can show a
    clear "no longer available" state instead of a checkout surprise.
    """
    items = (
        cart.items.select_related(
            "product", "product__category", "product__brand", "variant",
            # variant__product: pricing.stock_status_for() falls back to
            # instance.product.low_stock_threshold for variants, and the
            # variant instances created by select_related("variant") have
            # no cached `product` -- without this join, every variant
            # line lazily fetches its parent product (an N+1). The
            # reverse-manager FK back-fill that saves the catalog's own
            # detail view doesn't apply to select_related results.
            "variant__product",
        )
        .prefetch_related(
            Prefetch("product__images", queryset=ProductImage.objects.order_by("-is_primary", "ordering")),
            "variant__attribute_values__attribute",
        )
        .order_by("-created_at")
    )

    lines = []
    subtotal = 0
    item_count = 0

    for item in items:
        item_count += item.quantity
        reason = None

        if not item.product.is_active:
            reason = "product_unavailable"
        elif item.variant_id and not item.variant.is_active:
            reason = "variant_unavailable"
        else:
            available = _available_stock(item.product, item.variant)
            if item.quantity > available:
                reason = "insufficient_stock"

        is_available = reason is None
        price_info = (
            pricing.price_info_for_variant(item.variant)
            if item.variant_id
            else pricing.price_info_for_product(item.product)
        )
        stock_status = pricing.stock_status_for(item.variant if item.variant_id else item.product)
        line_total = price_info.price * item.quantity

        if is_available:
            subtotal += line_total

        lines.append(
            CartLineView(
                item=item,
                price_info=price_info,
                stock_status=stock_status,
                is_available=is_available,
                unavailable_reason=reason,
                line_total=line_total,
            )
        )

    return {
        "cart": cart,
        "lines": lines,
        "item_count": item_count,
        "subtotal": subtotal,
        "total": subtotal,
    }
