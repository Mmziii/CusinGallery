"""
Discounts views (coupon validation endpoint).

One endpoint: POST /discounts/coupons/validate/ -- "would this code
apply to MY cart right now, and what would it take off?" The server
computes everything from the caller's live cart; the client supplies
only the code. This is the preview checkout uses under the hood too (see
apps.discounts.services), so the number a customer sees before placing
the order is the number the order actually gets.
"""
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart import services as cart_services

from . import services as discount_services


class ValidateCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)


class CouponValidationResultSerializer(serializers.Serializer):
    code = serializers.CharField()
    discount_type = serializers.CharField()
    discount_amount = serializers.IntegerField()
    eligible_subtotal = serializers.IntegerField()
    cart_subtotal = serializers.IntegerField()


class ValidateCouponView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ValidateCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]

        cart = cart_services.get_or_create_cart(request.user)
        cart_view = cart_services.build_cart_view(cart)

        try:
            evaluation = discount_services.validate_and_calculate(request.user, code, cart_view)
        except discount_services.CouponError as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            CouponValidationResultSerializer(
                {
                    "code": evaluation.coupon.code,
                    "discount_type": evaluation.coupon.discount_type,
                    "discount_amount": evaluation.discount_amount,
                    "eligible_subtotal": evaluation.eligible_subtotal,
                    "cart_subtotal": cart_view["subtotal"],
                }
            ).data
        )
