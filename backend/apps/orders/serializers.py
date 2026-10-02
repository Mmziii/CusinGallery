"""
Orders serializers.
"""
from rest_framework import serializers

from apps.accounts import validators as account_validators
from apps.accounts.models import phone_validator

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    """
    Read-only -- OrderItems are only ever created by
    apps.orders.services.checkout(), never written directly through the
    API. product_slug is a convenience for a "view this product again"
    link; product_id/variant_id may be null if the catalog row was later
    deleted (SET_NULL, per apps.orders.models.OrderItem) -- the snapshot
    fields (product_name, sku, unit_price, total_price) are what the
    order actually displays regardless.
    """

    product_id = serializers.IntegerField(read_only=True)
    variant_id = serializers.IntegerField(read_only=True)
    product_slug = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id", "product_id", "variant_id", "product_slug",
            "product_name", "sku", "unit_price", "quantity", "total_price",
        ]
        read_only_fields = fields

    def get_product_slug(self, obj):
        return obj.product.slug if obj.product_id else None


class OrderSerializer(serializers.ModelSerializer):
    """Read-only -- list/detail representation of a placed order."""

    items = OrderItemSerializer(many=True, read_only=True)
    coupon_code = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "payment_status",
            "subtotal", "discount_amount", "shipping_cost", "total",
            "coupon_code",
            "shipping_recipient_name", "shipping_phone", "shipping_province",
            "shipping_city", "shipping_address", "shipping_postal_code",
            "shipping_unit", "shipping_building_number",
            "items", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_coupon_code(self, obj):
        return obj.coupon.code if obj.coupon_id else None


class CheckoutSerializer(serializers.Serializer):
    """
    Input for POST /orders/checkout/. Exactly one of two shapes:
        - {"address_id": <id of one of the caller's own saved addresses>}
        - the full inline address fields (a one-off address not saved to
          the account)

    Deliberately carries no price, quantity, or total field of any kind
    -- there is nothing here for a malicious/buggy client payload to
    override even if it tried; see apps.orders.services.checkout for
    where every monetary value actually comes from.
    """

    address_id = serializers.IntegerField(required=False)
    # Optional coupon. The client sends ONLY the code -- validity, scope,
    # and the Toman amount are computed entirely server-side (see
    # apps.discounts.services). There is deliberately no field for a
    # discount amount anywhere in this serializer.
    coupon_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    recipient_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=20, required=False, validators=[phone_validator])
    province = serializers.CharField(max_length=100, required=False)
    city = serializers.CharField(max_length=100, required=False)
    address = serializers.CharField(required=False)
    postal_code = serializers.CharField(max_length=20, required=False)
    unit = serializers.CharField(max_length=20, required=False, allow_blank=True)
    building_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    _REQUIRED_INLINE_FIELDS = ["recipient_name", "phone", "province", "city", "address", "postal_code"]

    def validate_postal_code(self, value):
        # Only actually required when address_id isn't used (see
        # validate() below) -- if present at all, though, it must be a
        # real postal code. Reuses the exact same rule
        # apps.accounts.serializers.AddressSerializer uses, not a second
        # copy of it.
        return account_validators.validate_postal_code(value)

    def validate(self, attrs):
        if attrs.get("address_id") is not None:
            return attrs

        missing = [f for f in self._REQUIRED_INLINE_FIELDS if not attrs.get(f)]
        if missing:
            raise serializers.ValidationError(
                {
                    "address_id": [
                        "Provide either address_id or all of: "
                        + ", ".join(self._REQUIRED_INLINE_FIELDS)
                        + f". Missing: {', '.join(missing)}."
                    ]
                }
            )
        return attrs
