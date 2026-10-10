"""
Customer invoice tests (Part 2): ownership (someone else's order 404s),
paid-only, snapshot + store info rendered, and the gift message is
escaped in the printed document.
"""
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.helpers import make_user
from apps.core.models import SiteSettings
from apps.core.testing import CacheIsolatedAPITestCase
from apps.payments.gateways.mock import _sign
from apps.payments.services import handle_callback, initiate_payment

from ..models import Order
from .helpers import add_to_cart, make_product

CB = "http://testserver/api/v1/payments/callback/"


class InvoiceAccessTests(CacheIsolatedAPITestCase):
    def _paid_order(self, user, gift_message=""):
        product = make_product(price=150000, stock_quantity=5)
        add_to_cart(user, product, quantity=1)
        from ..serializers import CheckoutSerializer
        from ..services import checkout

        serializer = CheckoutSerializer(data={
            "recipient_name": "Invoice Buyer", "phone": "+989121112233",
            "province": "Tehran", "city": "Tehran", "address": "St 1",
            "postal_code": "1234567890",
            "building_number": "10", "unit": "3",
            **({"gift_wrap": True, "gift_message": gift_message} if gift_message else {}),
        })
        serializer.is_valid(raise_exception=True)
        with override_settings(GIFT_WRAP_FEE=10000):
            order = checkout(user, serializer.validated_data)
        payment = initiate_payment(user, order.pk, callback_url=CB)["payment"]
        handle_callback({"authority": payment.gateway_transaction_id, "status": "ok",
                         "sig": _sign(payment.gateway_transaction_id, "ok")})
        order.refresh_from_db()
        return order

    def test_invoice_requires_login(self):
        response = self.client.get(reverse("order-invoice", args=[1]))
        self.assertIn(response.status_code, (401, 403))

    def test_someone_elses_order_is_404(self):
        owner = make_user(phone="+989540000001")
        order = self._paid_order(owner)
        intruder = make_user(phone="+989540000002")
        self.client.login(username="+989540000002", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-invoice", args=[order.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unpaid_order_is_404_even_for_its_owner(self):
        user = make_user(phone="+989540000003")
        product = make_product(stock_quantity=5)
        add_to_cart(user, product, quantity=1)
        from ..serializers import CheckoutSerializer
        from ..services import checkout

        serializer = CheckoutSerializer(data={
            "recipient_name": "U", "phone": "+989121112233",
            "province": "T", "city": "T", "address": "X", "postal_code": "1234567890",
            "building_number": "10", "unit": "3",
        })
        serializer.is_valid(raise_exception=True)
        order = checkout(user, serializer.validated_data)

        self.client.login(username="+989540000003", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-invoice", args=[order.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_paid_invoice_shows_snapshot_store_info_and_escapes_message(self):
        site = SiteSettings.load()
        site.phone = "+98 21 4444 5555"
        site.save()

        user = make_user(phone="+989540000004")
        order = self._paid_order(user, gift_message="<script>alert(1)</script>")
        self.client.login(username="+989540000004", password="a-strong-passw0rd!")

        response = self.client.get(reverse("order-invoice", args=[order.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        html = response.content.decode()
        self.assertIn(order.order_number, html)
        self.assertIn("بسته‌بندی هدیه", html)
        self.assertIn("&lt;script&gt;", html)          # escaped, never raw
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("کازین گالری", html)
        self.assertIn("۴۴۴", html)                     # Persian digits
        self.assertIn("چاپ / ذخیره به PDF", html)
