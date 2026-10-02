"""
Coupon + checkout + payment integration tests: coupons applied through
the REAL checkout pipeline, discount math reflected in order totals,
invalid coupons refusing to create orders, and CouponUsage rows written
only when the order is actually PAID.
"""
from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from apps.orders.models import Order
from apps.payments.services import handle_callback, initiate_payment

from ..models import Coupon, CouponUsage
from .helpers import add_to_cart, make_coupon, make_product, make_user

CHECKOUT_URL = reverse("checkout")
CALLBACK = "http://testserver/api/v1/payments/callback/"


def address_payload(**overrides):
    payload = {
        "recipient_name": "Coupon Customer",
        "phone": "+989121234567",
        "province": "Tehran",
        "city": "Tehran",
        "address": "Valiasr St, No. 10",
        "postal_code": "1234567890",
    }
    payload.update(overrides)
    return payload


class CheckoutWithCouponTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989510000001")
        self.product = make_product(price=100000, stock_quantity=50)
        add_to_cart(self.user, self.product, quantity=2)  # subtotal 200000
        self.client.login(username="+989510000001", password="a-strong-passw0rd!")

    def test_checkout_applies_valid_coupon_server_side(self):
        make_coupon("WELCOME10", percentage_value=10)
        response = self.client.post(
            CHECKOUT_URL, address_payload(coupon_code="WELCOME10"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

        order = Order.objects.get(user=self.user)
        self.assertEqual(order.subtotal, 200000)
        self.assertEqual(order.discount_amount, 20000)
        self.assertEqual(order.total, order.subtotal + order.shipping_cost - order.discount_amount)
        self.assertEqual(order.coupon.code, "WELCOME10")
        self.assertEqual(response.data["discount_amount"], 20000)
        self.assertEqual(response.data["coupon_code"], "WELCOME10")

    def test_checkout_without_coupon_still_zero_discount(self):
        response = self.client.post(CHECKOUT_URL, address_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.discount_amount, 0)
        self.assertIsNone(order.coupon)

    def test_blank_coupon_code_is_ignored(self):
        response = self.client.post(CHECKOUT_URL, address_payload(coupon_code="  "), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.get(user=self.user).discount_amount, 0)

    def test_invalid_coupon_fails_checkout_and_creates_no_order(self):
        response = self.client.post(
            CHECKOUT_URL, address_payload(coupon_code="DOESNOTEXIST"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("coupon_code", response.data)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)
        # Cart is untouched on a failed checkout.
        self.assertEqual(self.user.cart.items.count(), 1)

    def test_expired_coupon_fails_checkout(self):
        from .helpers import in_past

        make_coupon("EXPIRED", expiration_date=in_past(days=1))
        response = self.client.post(CHECKOUT_URL, address_payload(coupon_code="EXPIRED"), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_there_is_no_client_field_for_discount_amount(self):
        """The checkout contract accepts no price/discount input. Sending
        one must not change what the server computes."""
        make_coupon("TEN", percentage_value=10)
        response = self.client.post(
            CHECKOUT_URL,
            {**address_payload(coupon_code="TEN"), "discount_amount": 199999, "total": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.discount_amount, 20000)
        self.assertGreater(order.total, 190000)


class CouponUsageRecordingTests(CacheIsolatedAPITestCase):
    """CouponUsage must be written at PAYMENT success -- never at
    checkout -- so unpaid abandoned orders don't burn coupon quota."""

    def setUp(self):
        self.user = make_user(phone="+989510000010")
        self.product = make_product(price=100000, stock_quantity=50)
        add_to_cart(self.user, self.product, quantity=1)
        self.client.login(username="+989510000010", password="a-strong-passw0rd!")

    def _checkout_with(self, code):
        return self.client.post(CHECKOUT_URL, address_payload(coupon_code=code), format="json")

    def test_usage_recorded_only_after_successful_payment(self):
        coupon = make_coupon("PAYME", percentage_value=10)
        self.assertEqual(self._checkout_with("PAYME").status_code, status.HTTP_201_CREATED)
        self.assertEqual(CouponUsage.objects.filter(coupon=coupon).count(), 0)

        order = Order.objects.get(user=self.user)
        payment = initiate_payment(self.user, order.pk, callback_url=CALLBACK)["payment"]
        from apps.payments.gateways.mock import _sign

        handle_callback({"authority": payment.gateway_transaction_id, "status": "ok", "sig": _sign(payment.gateway_transaction_id, "ok")})

        usage = CouponUsage.objects.get(coupon=coupon)
        self.assertEqual(usage.user, self.user)
        self.assertEqual(usage.order, order)

    def test_usage_limit_blocks_second_checkout_after_first_paid(self):
        coupon = make_coupon("SINGLEUSE", percentage_value=10, usage_limit=1)
        self.assertEqual(self._checkout_with("SINGLEUSE").status_code, status.HTTP_201_CREATED)

        order = Order.objects.get(user=self.user)
        payment = initiate_payment(self.user, order.pk, callback_url=CALLBACK)["payment"]
        from apps.payments.gateways.mock import _sign

        handle_callback({"authority": payment.gateway_transaction_id, "status": "ok", "sig": _sign(payment.gateway_transaction_id, "ok")})
        self.assertEqual(CouponUsage.objects.filter(coupon=coupon).count(), 1)

        # Second order attempt with the same coupon must now fail.
        add_to_cart(self.user, make_product(price=50000), quantity=1)
        response = self._checkout_with("SINGLEUSE")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_per_user_limit_blocks_second_paid_use_by_same_user(self):
        coupon = make_coupon("ONCEEACH", percentage_value=10, per_user_usage_limit=1)
        self.assertEqual(self._checkout_with("ONCEEACH").status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(user=self.user)

        from apps.payments.gateways.mock import _sign

        payment = initiate_payment(self.user, order.pk, callback_url=CALLBACK)["payment"]
        handle_callback({"authority": payment.gateway_transaction_id, "status": "ok", "sig": _sign(payment.gateway_transaction_id, "ok")})

        # Paid once; a fresh cart can't use it again.
        add_to_cart(self.user, make_product(price=70000), quantity=1)
        response = self._checkout_with("ONCEEACH")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ValidateCouponEndpointTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989510000020")
        self.product = make_product(price=100000, stock_quantity=50)
        add_to_cart(self.user, self.product, quantity=2)
        self.url = reverse("coupon-validate")
        self.client.login(username="+989510000020", password="a-strong-passw0rd!")

    def test_requires_authentication(self):
        self.client.logout()
        response = self.client.post(self.url, {"code": "X"}, format="json")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_valid_code_returns_server_computed_discount(self):
        make_coupon("PREVIEW20", percentage_value=20)
        response = self.client.post(self.url, {"code": "PREVIEW20"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["discount_amount"], 40000)  # 20% of 200000
        self.assertEqual(response.data["eligible_subtotal"], 200000)
        self.assertEqual(response.data["cart_subtotal"], 200000)
        self.assertEqual(response.data["discount_type"], Coupon.DiscountType.PERCENTAGE)

    def test_invalid_code_returns_400(self):
        response = self.client.post(self.url, {"code": "NOPE"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_cart_is_rejected(self):
        make_coupon("ANY")
        self.user.cart.items.all().delete()
        response = self.client.post(self.url, {"code": "ANY"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
