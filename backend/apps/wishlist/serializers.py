"""
Wishlist serializers.

Reuses apps.products.serializers.ProductListSerializer for the nested
product rather than inventing a second "product summary" shape --
a wishlist page needs essentially the same card info (image, price,
stock status) a product listing does. This does NOT couple the wishlist
and cart domains to each other (see master spec step 14 -- "do NOT
tightly couple the two systems") -- both independently depend on
apps.products, which is the intended, shared reuse target, not a
cart<->wishlist dependency.
"""
from rest_framework import serializers

from apps.products.serializers import ProductListSerializer

from .models import WishlistItem


class WishlistItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    # Distinct from ProductListSerializer's own is_in_stock/stock_status
    # (which describe purchasability) -- this flags whether the product
    # is still active/published at all. A previously-wishlisted product
    # that's since been deactivated stays in the response (never
    # silently dropped, so the customer doesn't lose track of their
    # list) but is flagged here rather than presented as a normal,
    # currently-purchasable item -- see master spec step 13.
    is_available = serializers.BooleanField(source="product.is_active", read_only=True)

    class Meta:
        model = WishlistItem
        fields = ["id", "product", "is_available", "created_at"]


class AddWishlistItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()


class WishlistCheckSerializer(serializers.Serializer):
    """Input for GET /wishlist/check/?product=<id> -- validates the raw
    query param before it ever reaches a queryset filter."""

    product = serializers.IntegerField()
