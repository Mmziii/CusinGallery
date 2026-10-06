"""
Orders serializers.
"""
from rest_framework import serializers

from apps.accounts import validators as account_validators

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
    # Part R1: lets the storefront show the shared brand placeholder in the
    # image area of order lines when the product has no (more) image.
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id", "product_id", "variant_id", "product_slug",
            "product_name", "sku", "unit_price", "quantity", "total_price",
            "product_image",
        ]

    def get_product_image(self, obj):
        from apps.core.image_files import media_url

        product = obj.product
        if not product:
            return None
        # Read from the prefetch cache (see _order_queryset) -- a .filter()
        # here would issue one query per item (N+1).
        images = list(product.images.all())
        image = next((img for img in images if img.is_primary), None) or (images[0] if images else None)
        if not image or not image.image:
            return None
        return {
            "image": image.image.url,
            "webp_400": media_url(image.webp_400),
            "webp_800": media_url(image.webp_800),
            "webp_1200": media_url(image.webp_1200),
        }
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
            "shipping_method", "estimated_delivery_min", "estimated_delivery_max",
            "shipping_recipient_name", "shipping_phone", "shipping_province",
            "shipping_city", "shipping_address", "shipping_postal_code",
            "shipping_unit", "shipping_building_number",
            "gift_wrap", "gift_message", "gift_wrap_fee",
            "items", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_coupon_code(self, obj):
        return obj.coupon.code if obj.coupon_id else None


from apps.core.serializers import NullToBlankTextMixin


class CheckoutSerializer(NullToBlankTextMixin, serializers.Serializer):
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
    # Optional shipping method. The client only PICKS from the configured
    # methods (settings.SHIPPING_METHODS, see apps.orders.shipping) --
    # the cost and delivery window for whichever method is chosen are
    # computed entirely server-side at checkout; there is no field here
    # for a client to supply either. Blank/missing means the default
    # (standard) method.
    shipping_method = serializers.CharField(max_length=20, required=False, allow_blank=True)
    # Gift wrapping (Part 2): opt-in flag + optional short message. The
    # FEE is never accepted from the client -- the server applies
    # settings.GIFT_WRAP_FEE (0 hides the feature entirely).
    gift_wrap = serializers.BooleanField(required=False, default=False)
    gift_message = serializers.CharField(
        required=False, allow_blank=True, max_length=200,
        trim_whitespace=True,
    )
    # Optional coupon. The client sends ONLY the code -- validity, scope,
    # and the Toman amount are computed entirely server-side (see
    # apps.discounts.services). There is deliberately no field for a
    # discount amount anywhere in this serializer.
    coupon_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    recipient_name = serializers.CharField(max_length=150, required=False)
    # Part S1 (item 3): same normalizing rules as saved addresses --
    # Persian digits accepted and normalized, Iranian mobile/landline only
    # (validate_phone below; it also stores the normalized form).
    phone = serializers.CharField(max_length=20, required=False)
    province = serializers.CharField(max_length=100, required=False)
    city = serializers.CharField(max_length=100, required=False)
    address = serializers.CharField(required=False)
    postal_code = serializers.CharField(max_length=20, required=False)
    unit = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    building_number = serializers.CharField(
        max_length=20, required=False, allow_blank=True, allow_null=True
    )

    _REQUIRED_INLINE_FIELDS = ["recipient_name", "phone", "province", "city", "address", "postal_code"]

    def to_internal_value(self, data):
        # JSON clients may send null for the optional unit/building_number;
        # downstream code (order snapshot, optional saved address) expects "".
        if isinstance(data, dict):
            data = dict(data)
            for key in ("unit", "building_number"):
                if data.get(key) is None and key in data:
                    data[key] = ""
        return super().to_internal_value(data)

    def validate_shipping_method(self, value):
        from . import shipping

        value = (value or "").strip()
        if not value:
            return shipping.DEFAULT_METHOD
        if not shipping.is_valid_shipping_method(value):
            valid = ", ".join(shipping.get_shipping_methods())
            raise serializers.ValidationError(
                f"'{value}' is not an available shipping method. Choose one of: {valid}."
            )
        return value

    def validate_phone(self, value):
        # Same rule as saved addresses; blank phone stays blank (it is
        # only required for address-bearing methods -- see validate()).
        if not value:
            return value
        return account_validators.validate_address_phone(value)

    def validate_postal_code(self, value):
        # Only actually required when address_id isn't used (see
        # validate() below) -- if present at all, though, it must be a
        # real postal code. Reuses the exact same rule
        # apps.accounts.serializers.AddressSerializer uses, not a second
        # copy of it.
        return account_validators.validate_postal_code(value)

    def validate_unit(self, value):
        # Part S5 item 6: «۰» is valid, letters are not. Emptiness is
        # judged in validate() (a saved address may legitimately have
        # none -- those orders are snapshots and stay valid).
        return account_validators.validate_unit(value) if value else ""

    def validate_building_number(self, value):
        return account_validators.validate_building_number(value) if value else ""

    def validate(self, attrs):
        if attrs.get("address_id") is not None:
            return attrs

        from . import shipping

        method = attrs.get("shipping_method") or shipping.DEFAULT_METHOD
        if not shipping.get_shipping_methods()[method].get("requires_address", True):
            # Pickup (Part 1): no delivery address exists -- but the store
            # still needs to know WHO picks the order up.
            missing = [f for f in ("recipient_name", "phone") if not attrs.get(f)]
            if missing:
                raise serializers.ValidationError(
                    {
                        "recipient_name": [
                            "Pickup orders need at least recipient_name and phone. "
                            f"Missing: {', '.join(missing)}."
                        ]
                    }
                )
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
        # Part S5 item 6: a one-off checkout address needs the plot number
        # and the unit too (field-keyed Persian messages, so the storefront
        # can show them inline). The `address_id` path above is untouched,
        # which is what keeps saved legacy addresses orderable.
        plot_unit_errors = {
            field: [account_validators.PLOT_UNIT_MESSAGES[field]]
            for field in ("building_number", "unit")
            if not (attrs.get(field) or "").strip()
        }
        if plot_unit_errors:
            raise serializers.ValidationError(plot_unit_errors)
        return attrs
