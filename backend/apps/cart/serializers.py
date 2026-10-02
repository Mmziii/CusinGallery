"""
Cart serializers.

Deliberately compose Phase 4's existing serializers (PriceInfoSerializer,
ProductImageSerializer, ProductAttributeValueSerializer) rather than
re-implementing price/image/attribute rendering here -- same "single
mechanism, not duplicated per view" principle Phase 4 established for
pricing, extended to these too.

CartItemSerializer/CartSerializer serialize the plain dicts/dataclasses
`apps.cart.services.build_cart_view()` returns, not bare model instances
-- pricing and availability are computed fresh on every read, never
stored on CartItem itself.
"""
from rest_framework import serializers

from apps.products.serializers import (
    PriceInfoSerializer,
    ProductAttributeValueSerializer,
    ProductImageSerializer,
)


class CartItemProductSerializer(serializers.Serializer):
    """Lightweight product summary for a cart line -- not the full
    catalog ProductDetailSerializer, which would pull in fields (full
    description, all variants, related products, ...) irrelevant here."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    primary_image = serializers.SerializerMethodField()

    def get_primary_image(self, obj):
        # Relies on the queryset having prefetched `images` ordered
        # primary-first (see cart.services.build_cart_view) -- reads
        # from that prefetch cache, not a fresh query per cart line.
        images = list(obj.images.all())
        return ProductImageSerializer(images[0], context=self.context).data if images else None


class CartItemVariantSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    attribute_values = ProductAttributeValueSerializer(many=True)


class CartItemSerializer(serializers.Serializer):
    """Serializes a cart.services.CartLineView."""

    id = serializers.SerializerMethodField()
    product = serializers.SerializerMethodField()
    variant = serializers.SerializerMethodField()
    quantity = serializers.SerializerMethodField()
    price_info = serializers.SerializerMethodField()
    line_total = serializers.IntegerField()
    stock_status = serializers.CharField()
    is_available = serializers.BooleanField()
    unavailable_reason = serializers.CharField(allow_null=True)

    def get_id(self, obj):
        return obj.item.id

    def get_product(self, obj):
        return CartItemProductSerializer(obj.item.product, context=self.context).data

    def get_variant(self, obj):
        if not obj.item.variant_id:
            return None
        return CartItemVariantSerializer(obj.item.variant, context=self.context).data

    def get_quantity(self, obj):
        return obj.item.quantity

    def get_price_info(self, obj):
        return PriceInfoSerializer(obj.price_info).data


class CartSerializer(serializers.Serializer):
    """Serializes the dict returned by cart.services.build_cart_view().

    `shipping_cost_preview` is what shipping WOULD cost for this cart's
    subtotal, computed by the same centralized function checkout uses
    (apps.orders.shipping) -- so the cart/checkout UI can show a real
    number without duplicating the threshold logic client-side. The
    authoritative value is still written by checkout itself.
    """

    id = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    item_count = serializers.IntegerField()
    subtotal = serializers.IntegerField()
    total = serializers.IntegerField()
    shipping_cost_preview = serializers.SerializerMethodField()

    def get_id(self, obj):
        return obj["cart"].id

    def get_items(self, obj):
        return CartItemSerializer(obj["lines"], many=True, context=self.context).data

    def get_shipping_cost_preview(self, obj):
        from apps.orders.shipping import calculate_shipping_cost

        return calculate_shipping_cost(obj["subtotal"])


class AddCartItemSerializer(serializers.Serializer):
    """Input for POST /cart/items/. Only ever a product/variant
    identifier and a quantity -- the client can never supply a price
    (see master spec step 3/20: "the client must never be able to
    manipulate price/subtotal/total")."""

    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)


class UpdateCartItemSerializer(serializers.Serializer):
    """Input for PATCH /cart/items/{id}/. 0 is explicitly allowed here
    (unlike AddCartItemSerializer's min_value=1) -- see
    cart.services.update_item_quantity for what a 0 does."""

    quantity = serializers.IntegerField(min_value=0)
