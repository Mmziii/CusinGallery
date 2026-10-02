"""
Payment API surface tests (Phase 7): detail-endpoint ownership, the mock
gateway's hosted page, the full end-to-end redirect flow, and a threaded
duplicate-callback race proving inventory is decremented exactly once
even under concurrency.
"""
import threading
from unittest import skipIf

from django.db import connection
from django.urls import reverse
from rest_framework import status

from apps.core.testing import (
    CacheIsolatedAPITestCase,
    CacheIsolatedAPITransactionTestCase,
)
from apps.orders.models import Order

from ..gateways.mock import _sign
from ..models import Payment
from ..services import initiate_payment
from .helpers import make_unpaid_order, make_user

CALLBACK = "http://testserver/api/v1/payments/callback/"


class PaymentDetailOwnershipTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.owner = make_user(phone="+989420000001")
        self.order = make_unpaid_order(self.owner)
        self.payment = initiate_payment(self.owner, self.order.pk, callback_url=CALLBACK)["payment"]

    def test_owner_can_see_payment(self):
        self.client.login(username="+989420000001", password="a-strong-passw0rd!")
        response = self.client.get(reverse("payment-detail", args=[self.payment.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.payment.pk)
        self.assertEqual(response.data["order_number"], self.order.order_number)
        self.assertEqual(response.data["amount"], self.order.total)

    def test_anonymous_cannot_see_payment(self):
        response = self.client.get(reverse("payment-detail", args=[self.payment.pk]))
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_other_user_gets_404_not_403(self):
        intruder = make_user(phone="+989420000002")
        intruder.set_password("a-strong-passw0rd!")
        intruder.save()
        self.client.login(username="+989420000002", password="a-strong-passw0rd!")
        response = self.client.get(reverse("payment-detail", args=[self.payment.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MockGatewayPageTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989420000010")
        self.order = make_unpaid_order(self.user)
        self.payment = initiate_payment(self.user, self.order.pk, callback_url=CALLBACK)["payment"]
        self.authority = self.payment.gateway_transaction_id

    def test_page_shows_pay_and_cancel_links(self):
        response = self.client.get(reverse("mock-gateway-page", args=[self.authority]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        html = response.content.decode()
        self.assertIn("status=ok", html)
        self.assertIn("status=cancelled", html)
        self.assertIn(self.order.order_number, html)
        self.assertIn(str(self.order.total), html)

    def test_page_never_exposes_the_signature_secret(self):
        response = self.client.get(reverse("mock-gateway-page", args=[self.authority]))
        from django.conf import settings

        secret = settings.PAYMENT_MERCHANT_ID or settings.SECRET_KEY
        self.assertNotIn(secret, response.content.decode())

    def test_unknown_authority_renders_not_found_page(self):
        response = self.client.get(reverse("mock-gateway-page", args=["deadbeef" * 4]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("تراکنش یافت نشد", response.content.decode())


class EndToEndFlowTests(CacheIsolatedAPITestCase):
    """The complete customer journey, driven only through real endpoints:
    checkout -> initiate -> gateway page -> callback -> result page data."""

    def test_full_successful_payment_flow(self):
        user = make_user(phone="+989420000020")
        order = make_unpaid_order(user)
        product = order.items.first().product
        stock_before = product.stock_quantity

        self.client.login(username="+989420000020", password="a-strong-passw0rd!")

        initiated = self.client.post(
            reverse("payment-initiate"), {"order_id": order.pk}, format="json"
        )
        self.assertEqual(initiated.status_code, status.HTTP_201_CREATED)
        # The authority lives on the gateway side of the flow; the API
        # serializer deliberately doesn't expose it, so read it like the
        # gateway would.
        authority = Payment.objects.get(pk=initiated.data["payment"]["id"]).gateway_transaction_id

        page = self.client.get(reverse("mock-gateway-page", args=[authority]))
        self.assertEqual(page.status_code, status.HTTP_200_OK)

        callback = self.client.get(
            reverse("payment-callback"),
            {"authority": authority, "status": "ok", "sig": _sign(authority, "ok")},
        )
        self.assertEqual(callback.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=success", callback["Location"])

        payment_id = initiated.data["payment"]["id"]
        detail = self.client.get(reverse("payment-detail", args=[payment_id]))
        self.assertEqual(detail.data["status"], Payment.Status.SUCCESS)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, stock_before - order.items.first().quantity)

    def test_full_cancelled_payment_flow(self):
        user = make_user(phone="+989420000021")
        order = make_unpaid_order(user)
        self.client.login(username="+989420000021", password="a-strong-passw0rd!")

        initiated = self.client.post(
            reverse("payment-initiate"), {"order_id": order.pk}, format="json"
        )
        authority = Payment.objects.get(pk=initiated.data["payment"]["id"]).gateway_transaction_id

        callback = self.client.get(
            reverse("payment-callback"),
            {"authority": authority, "status": "cancelled", "sig": _sign(authority, "cancelled")},
        )
        self.assertEqual(callback.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=cancelled", callback["Location"])

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)


@skipIf(
    connection.vendor == "sqlite",
    "SQLite locks the entire database file while any write transaction "
    "is open, so two threads racing through the callback flow hit "
    "'database table is locked' errors that PostgreSQL's row-level "
    "locking (which production uses, and which this test is meant to "
    "exercise) never produces. Run against PostgreSQL instead.",
)
class ConcurrentCallbackTests(CacheIsolatedAPITransactionTestCase):
    """
    Two callbacks for the same attempt arriving at the same instant must
    still decrement inventory exactly once. TransactionTestCase (not the
    usual APITestCase) because real threads need to see each other's
    committed rows, which test-internal savepoint wrapping would hide.
    """

    def test_simultaneous_callbacks_decrement_stock_exactly_once(self):
        from django.db import connections
        from django.test import Client

        user = make_user(phone="+989420000030")
        order = make_unpaid_order(user)
        product = order.items.first().product
        stock_before = product.stock_quantity
        payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]
        authority = payment.gateway_transaction_id
        params = {"authority": authority, "status": "ok", "sig": _sign(authority, "ok")}

        results = []
        barrier = threading.Barrier(2)

        def fire():
            try:
                barrier.wait(timeout=10)
                client = Client()
                response = client.get(reverse("payment-callback"), params)
                results.append(response.status_code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=fire) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(results, [status.HTTP_302_FOUND, status.HTTP_302_FOUND])
        self.assertEqual(
            Payment.objects.filter(order=order, status=Payment.Status.SUCCESS).count(), 1
        )
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, stock_before - order.items.first().quantity)
