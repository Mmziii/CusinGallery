"""Task 1: server-side events that a browser beacon can never lose.

* authenticated add/remove through the cart API;
* checkout (order_placed, with province/city + anonymous session key);
* payment verification (order_paid, reusing the order's own session key).
"""
from django.urls import reverse
from rest_framework import status

from apps.core.testing import CacheIsolatedAPITestCase
from apps.orders.models import Order
from apps.orders.tests.helpers import (
    add_to_cart,
    make_product,
    make_user,
    valid_checkout_payload,
)
from apps.payments.gateways.mock import _sign
from apps.payments.models import Payment
from apps.payments.services import initiate_payment

from ..models import Event
from ..tracking import SESSION_HEADER

SESSION = "server-event-session-1"


class CartApiEventTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989430000001")
        self.product = make_product(name="قوری چینی")
        self.client.login(username="+989430000001", password="a-strong-passw0rd!")

    def test_add_to_cart_is_recorded_on_the_server(self):
        response = self.client.post(
            reverse("cart-item-create"),
            {"product_id": self.product.pk, "quantity": 2},
            format="json",
            HTTP_X_CUSIN_SESSION=SESSION,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(event_type=Event.Type.ADD_TO_CART)
        self.assertEqual(event.product_id, self.product.pk)
        self.assertEqual(event.user_id, self.user.pk)
        self.assertEqual(event.session_key, SESSION)

    def test_removing_the_line_is_recorded_too(self):
        item = add_to_cart(self.user, self.product, quantity=1)
        response = self.client.delete(
            reverse("cart-item-detail", args=[item.pk]),
            HTTP_X_CUSIN_SESSION=SESSION,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Event.objects.filter(
                event_type=Event.Type.REMOVE_FROM_CART, product=self.product,
            ).exists()
        )


class CheckoutEventTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989430000002")
        self.product = make_product(name="سرویس چای")
        add_to_cart(self.user, self.product, quantity=1)
        self.client.login(username="+989430000002", password="a-strong-passw0rd!")

    def test_order_placed_carries_the_session_and_the_order_location(self):
        response = self.client.post(
            reverse("checkout"),
            valid_checkout_payload(province="تهران", city="تهران"),
            format="json",
            HTTP_X_CUSIN_SESSION=SESSION,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get()
        event = Event.objects.get(event_type=Event.Type.ORDER_PLACED)
        self.assertEqual(event.order_id, order.pk)
        self.assertEqual(event.session_key, SESSION)
        self.assertEqual(event.province, "تهران")
        self.assertEqual(event.city, "تهران")
        self.assertEqual(event.user_id, self.user.pk)


class OrderPaidEventTests(CacheIsolatedAPITestCase):
    def test_payment_records_order_paid_and_reuses_the_placed_session(self):
        user = make_user(phone="+989430000003")
        product = make_product(name="دیگ مسی")
        add_to_cart(user, product, quantity=1)
        from apps.orders.services import checkout

        payload = {
            "recipient_name": "سارا احمدی",
            "phone": "+989121234567",
            "province": "اصفهان",
            "city": "کاشان",
            "address": "خیابان اصلی، پلاک ۲",
            "postal_code": "1234567890",
            "shipping_method": "standard",
        }
        order = checkout(user, payload, analytics_session_key=SESSION)

        initiated = initiate_payment(
            user, order.pk, callback_url="http://testserver/api/v1/payments/callback/",
        )
        payment = initiated["payment"]
        authority = Payment.objects.get(pk=payment.pk).gateway_transaction_id

        self.client.get(
            reverse("payment-callback"),
            {"authority": authority, "status": "ok", "sig": _sign(authority, "ok")},
        )

        event = Event.objects.get(event_type=Event.Type.ORDER_PAID)
        self.assertEqual(event.order_id, order.pk)
        self.assertEqual(event.session_key, SESSION)
        self.assertEqual(event.province, "اصفهان")
        self.assertEqual(event.city, "کاشان")

    def test_order_paid_without_a_placed_event_falls_back_to_the_user_session(self):
        """A payment callback has no browser key; the event still counts."""
        from apps.payments.tests.helpers import make_unpaid_order, make_user as pay_user

        user = pay_user(phone="+989430000004")
        order = make_unpaid_order(user)  # checkout without a session key
        # The order_placed event exists but has the u:<pk> fallback key.
        initiated = initiate_payment(
            user, order.pk, callback_url="http://testserver/api/v1/payments/callback/",
        )
        authority = Payment.objects.get(pk=initiated["payment"].pk).gateway_transaction_id
        self.client.get(
            reverse("payment-callback"),
            {"authority": authority, "status": "ok", "sig": _sign(authority, "ok")},
        )
        paid = Event.objects.get(event_type=Event.Type.ORDER_PAID)
        self.assertEqual(paid.session_key, f"u:{user.pk}")
