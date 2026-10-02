"""
Single source of truth for how price, compare-at price, and discount
information are derived for display (Phase 4). Every serializer that
needs to show a price uses these two functions instead of recomputing
this logic itself -- see master spec section 9: "Do not duplicate
pricing logic across serializers/views."

Two independent signals, deliberately not conflated:
    - `discount_percentage` is the admin-set badge value from
      Product.discount_percentage (Phase 2) -- shown exactly as entered,
      e.g. for a store-wide "15% OFF" campaign that isn't necessarily
      tied to a specific compare-at price.
    - `is_on_sale` / `discount_amount` / `compare_at_price` are derived
      purely from Product.price vs Product.compare_at_price (Phase 2's
      own constraint already guarantees compare_at_price >= price when
      set -- see Product.clean()).

These can disagree (a product could have compare_at_price unset but
discount_percentage=10, or vice versa) -- that's intentional, not a bug;
the frontend can choose which signal fits a given placement (a specific
struck-through price needs compare_at_price, a generic promo badge can
use discount_percentage alone).
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PriceInfo:
    price: int
    compare_at_price: Optional[int]
    discount_percentage: int
    is_on_sale: bool
    discount_amount: int


def price_info_for_product(product) -> PriceInfo:
    price = product.price
    compare_at = product.compare_at_price
    is_on_sale = bool(compare_at and compare_at > price)
    return PriceInfo(
        price=price,
        compare_at_price=compare_at if is_on_sale else None,
        discount_percentage=product.discount_percentage,
        is_on_sale=is_on_sale,
        discount_amount=(compare_at - price) if is_on_sale else 0,
    )


def price_info_for_variant(variant) -> PriceInfo:
    """
    If the variant overrides the price, the parent product's
    compare_at_price was set relative to the *product's* price, not this
    variant's -- applying it here would show a discount comparison that
    doesn't correspond to any real data, so a variant with its own price
    is shown plainly instead. A variant with no price override is, by
    definition, sold at the product's own price, so it inherits that
    product's full sale/discount picture.
    """
    if variant.price is not None:
        return PriceInfo(
            price=variant.price,
            compare_at_price=None,
            discount_percentage=0,
            is_on_sale=False,
            discount_amount=0,
        )
    return price_info_for_product(variant.product)


def stock_status_for(instance) -> str:
    """
    Coarse status only ("out_of_stock" / "low_stock" / "in_stock"), never
    the raw stock_quantity/low_stock_threshold numbers -- see master spec
    section 20: "do not expose internal inventory details beyond what
    the storefront needs." Works for both Product and ProductVariant,
    which share the same stock_quantity/low_stock_threshold shape via
    Phase 2's schema, except ProductVariant has no low_stock_threshold of
    its own -- it borrows the parent product's.
    """
    quantity = instance.stock_quantity
    threshold = getattr(instance, "low_stock_threshold", None)
    if threshold is None:
        threshold = instance.product.low_stock_threshold if hasattr(instance, "product") else 0

    if quantity <= 0:
        return "out_of_stock"
    if quantity <= threshold:
        return "low_stock"
    return "in_stock"
