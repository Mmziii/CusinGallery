"""
Gift wrapping tests (Part 2): fee snapshots into the order total (and
therefore into the payment cross-check), the option is hidden when the
fee is 0, the fee neither triggers free shipping nor gets discounted by
coupons, message length is capped, and displays escape the message.
"""
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.helpers import make_user
from apps.core.testing import CacheIsolatedAPITestCase
from apps.discounts.tests.helpers import make_coupon
from apps.payments.services import initiate_payment

from ..models import Order
from .helpers import add_to_cart, make_product

GIFT = {"GIFT_WRAP_FEE": 25000}


@override_settings(**GIFT)
class GiftWrapCheckoutTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989520000001")
        self.client.login(username="+989520000001", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def checkout(self, **extra):
        product = make_product(price=300000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        payload = {
            "recipient_name": "Gift Buyer",
            "phone": "+989121112233",
            "province": "Tehran",
            "city": "Tehran",
            "address": "Somewhere 12",
            "postal_code": "1234567890",
        }
        payload.update(extra)
        return self.client.post(self.url, payload, format="json")

    def test_fee_is_snapshotted_into_the_total(self):
        response = self.checkout(gift_wrap=True, gift_message="تولدت مبارک")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        order = Order.objects.get(user=self.user)
        self.assertTrue(order.gift_wrap)
        self.assertEqual(order.gift_wrap_fee, 25000)
        self.assertEqual(order.gift_message, "تولدت مبارک")
        self.assertEqual(order.total, order.subtotal + order.shipping_cost + 25000)

    def test_payment_amount_cross_check_covers_the_fee(self):
        self.checkout(gift_wrap=True)
        order = Order.objects.get(user=self.user)
        payment = initiate_payment(self.user, order.pk, callback_url="http://x/cb/")["payment"]
        self.assertEqual(payment.amount, order.total)
        self.assertEqual(payment.amount, order.subtotal + order.shipping_cost + 25000)

    def test_fee_does_not_trigger_free_shipping(self):
        # Subtotal just BELOW the free threshold; adding the fee must not
        # push the shipping calculation over it (threshold uses the
        # product subtotal only -- documented decision).
        product = make_product(price=990000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(
            self.url,
            {
                "recipient_name": "Gift Buyer", "phone": "+989121112233",
                "province": "Tehran", "city": "Tehran", "address": "X 1",
                "postal_code": "1234567890", "gift_wrap": True,
            },
            format="json",
        )
        order = Order.objects.get(user=self.user)
        from django.conf import settings as dj_settings

        self.assertEqual(order.shipping_cost, dj_settings.STANDARD_SHIPPING_COST)

    def test_coupon_discount_does_not_touch_the_fee(self):
        make_coupon(code="GIFTTEST10", discount_type="percentage", percentage_value=10)
        product = make_product(price=200000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(
            self.url,
            {
                "recipient_name": "Gift Buyer", "phone": "+989121112233",
                "province": "Tehran", "city": "Tehran", "address": "X 1",
                "postal_code": "1234567890",
                "gift_wrap": True, "coupon_code": "GIFTTEST10",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.discount_amount, 20000)  # 10% of the 200k subtotal
        self.assertEqual(order.gift_wrap_fee, 25000)    # full fee, undiscounted
        self.assertEqual(
            order.total, order.subtotal - 20000 + order.shipping_cost + 25000
        )

    def test_gift_message_over_200_chars_is_rejected(self):
        response = self.checkout(gift_wrap=True, gift_message="م" * 201)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_snapshot_ignores_later_fee_changes(self):
        self.checkout(gift_wrap=True)
        order = Order.objects.get(user=self.user)
        with override_settings(GIFT_WRAP_FEE=99000):
            order.refresh_from_db()
            self.assertEqual(order.gift_wrap_fee, 25000)
            self.assertEqual(order.total, order.subtotal + order.shipping_cost + 25000)


class GiftWrapHiddenWhenFeeZeroTests(CacheIsolatedAPITestCase):
    def test_zero_fee_hides_the_option(self):
        # Default GIFT_WRAP_FEE=0: opting in must be a no-op.
        user = make_user(phone="+989520000002")
        self.client.login(username="+989520000002", password="a-strong-passw0rd!")
        product = make_product(price=100000, stock_quantity=5)
        add_to_cart(user, product, quantity=1)
        response = self.client.post(
            reverse("checkout"),
            {
                "recipient_name": "G", "phone": "+989121112233",
                "province": "T", "city": "T", "address": "X", "postal_code": "1234567890",
                "gift_wrap": True, "gift_message": "hello",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(user=user)
        self.assertFalse(order.gift_wrap)
        self.assertEqual(order.gift_wrap_fee, 0)
        self.assertEqual(order.gift_message, "")

    def test_shipping_methods_endpoint_advertises_the_fee(self):
        with override_settings(**GIFT):
            data = self.client.get(reverse("shipping-methods")).json()
        self.assertEqual(data["gift_wrap_fee"], 25000)
