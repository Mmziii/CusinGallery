"""
Payment initiation tests (Phase 7).

Covers the POST /payments/initiate/ endpoint and the initiate_payment
service: ownership, payability rules, amount snapshotting, and the
gateway-failure path.
"""
from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.models import Order

from ..gateways.base import GatewayError
from ..models import Payment
from .helpers import make_unpaid_order, make_user

CALLBACK = "http://testserver/api/v1/payments/callback/"


class InitiatePaymentTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989400000001")
        self.order = make_unpaid_order(self.user)
        self.url = reverse("payment-initiate")
        self.client.login(username="+989400000001", password="a-strong-passw0rd!")

    def test_requires_authentication(self):
        self.client.logout()
        response = self.client.post(self.url, {"order_id": self.order.pk}, format="json")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_initiate_creates_pending_payment_for_own_unpaid_order(self):
        response = self.client.post(self.url, {"order_id": self.order.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, self.order.total)
        self.assertEqual(payment.gateway, "mock")
        self.assertTrue(payment.gateway_transaction_id)
        self.assertTrue(response.data["redirect_url"])

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_cannot_initiate_for_another_users_order(self):
        other = make_user(phone="+989400000002")
        other_order = make_unpaid_order(other)
        response = self.client.post(self.url, {"order_id": other_order.pk}, format="json")
        # 404, not 403 -- another user's order must look nonexistent.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Payment.objects.filter(order=other_order).count(), 0)

    def test_cannot_initiate_for_nonexistent_order(self):
        response = self.client.post(self.url, {"order_id": 999999}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_initiate_for_already_paid_order(self):
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.save(update_fields=["payment_status"])
        response = self.client.post(self.url, {"order_id": self.order.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 0)

    def test_cannot_initiate_for_cancelled_order(self):
        self.order.status = Order.Status.CANCELLED
        self.order.save(update_fields=["status"])
        response = self.client.post(self.url, {"order_id": self.order.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_repeated_initiation_creates_separate_attempts(self):
        """Retrying payment is legitimate (a first attempt can be
        cancelled/failed) -- each attempt gets its own Payment row."""
        first = self.client.post(self.url, {"order_id": self.order.pk}, format="json")
        second = self.client.post(self.url, {"order_id": self.order.pk}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 2)

    def test_gateway_failure_records_failed_payment_and_keeps_order_unpaid(self):
        with mock.patch(
            "apps.payments.services.get_gateway"
        ) as mock_gateway:
            gw = mock_gateway.return_value
            gw.name = "mock"
            gw.initiate.side_effect = GatewayError("gateway unreachable")

            response = self.client.post(self.url, {"order_id": self.order.pk}, format="json")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIn("gateway unreachable", payment.failure_reason)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.UNPAID)
