"""
Analytics scoping tests (Part 4): the optional analytics snippet lives
only in the storefront SPA bundle (frontend/src/components/Analytics
mounts it when the build env is configured). Server-rendered surfaces --
Django admin, the payment callback redirect and the customer invoice --
must never carry it, so analytics can't leak into admin or PSP-facing
pages. The frontend counterpart (env unset => nothing loads, DNT
respected) is covered by frontend/src/Analytics.test.jsx.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.tests.helpers import make_user
from apps.payments.tests.helpers import make_product


PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


@override_settings(**PLAIN_STATIC)
class AnalyticsScopingTests(TestCase):
    def test_admin_pages_carry_no_analytics_marker(self):
        response = self.client.get("/admin/login/", follow=True)
        self.assertNotContains(response, "data-cusin-analytics")

    def test_payment_callback_carry_no_analytics_marker(self):
        # The callback endpoint answers a redirect for the browser; even
        # error bodies must not embed storefront analytics.
        response = self.client.get("/payment/callback/", follow=False)
        # Redirect to the SPA result page; neither the redirect body nor
        # its target (a server template could only be the backend's) may
        # carry the storefront analytics marker.
        self.assertIn(response.status_code, (302, 400, 404))
        self.assertNotIn(b"data-cusin-analytics", response.content)

    def test_invoice_carries_no_analytics_marker(self):
        user = make_user(phone="+989550000001")
        self.client.login(username="+989550000001", password="a-strong-passw0rd!")
        from apps.orders.tests.helpers import add_to_cart
        from apps.orders.services import checkout
        from apps.orders.serializers import CheckoutSerializer

        product = make_product(stock_quantity=5)
        add_to_cart(user, product, quantity=1)
        serializer = CheckoutSerializer(data={
            "recipient_name": "A", "phone": "+989121112233",
            "province": "T", "city": "T", "address": "X", "postal_code": "1234567890",
        })
        serializer.is_valid(raise_exception=True)
        order = checkout(user, serializer.validated_data)
        from apps.payments.services import initiate_payment
        from apps.payments.gateways.mock import _sign
        from apps.payments.services import handle_callback

        payment = initiate_payment(user, order.pk, callback_url="http://x/cb/")["payment"]
        handle_callback({"authority": payment.gateway_transaction_id, "status": "ok",
                         "sig": _sign(payment.gateway_transaction_id, "ok")})
        response = self.client.get(reverse("order-invoice", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-cusin-analytics")
