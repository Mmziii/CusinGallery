"""
Payments serializers (Phase 7 - Payment architecture).
"""
from rest_framework import serializers

from .models import Payment


class InitiatePaymentSerializer(serializers.Serializer):
    """
    Input for POST /payments/initiate/ -- nothing but "which of my
    orders". The amount, gateway, and callback URL are all decided
    server-side (see services.initiate_payment); there is nothing here
    for a malicious client to override.
    """

    order_id = serializers.IntegerField()


class PaymentSerializer(serializers.ModelSerializer):
    """
    Read-only customer-facing representation of a payment attempt.
    Ownership scoping happens in the view's queryset, same 404-not-403
    pattern as orders/addresses/cart.
    """

    order_id = serializers.IntegerField(source="order.id", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    # The order's snapshotted shipping method + promised delivery window,
    # so the payment-result page can show "how will this reach me and
    # when" without a second fetch of the order.
    shipping_method = serializers.CharField(source="order.shipping_method", read_only=True)
    estimated_delivery_min = serializers.DateField(source="order.estimated_delivery_min", read_only=True)
    estimated_delivery_max = serializers.DateField(source="order.estimated_delivery_max", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "order_id", "order_number", "amount", "status",
            "gateway", "gateway_ref_id", "failure_reason", "paid_at", "created_at",
            "shipping_method", "estimated_delivery_min", "estimated_delivery_max",
        ]
        read_only_fields = fields
