"""
Payment callback / verification tests (Phase 7).

The callback is the security-critical path: it must be idempotent, must
never trust client-supplied success, must verify the gateway's own
signature, and must transition inventory exactly once. These tests drive
services.handle_callback through the mock gateway's REAL signing, plus
forged/tampered parameters to prove verification is actually enforced.
"""
from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from apps.orders.models import Order

from ..gateways.mock import _sign
from ..models import Payment
from ..services import PaymentError, handle_callback, initiate_payment
from .helpers import make_unpaid_order, make_user

CALLBACK = "http://testserver/api/v1/payments/callback/"


def signed_params(authority, outcome):
    """Parameters exactly as the (mock) gateway would send them back."""
    return {"authority": authority, "status": outcome, "sig": _sign(authority, outcome)}


class CallbackBase(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989410000001")
        self.order = make_unpaid_order(self.user)
        initiated = initiate_payment(self.user, self.order.pk, callback_url=CALLBACK)
        self.payment = initiated["payment"]
        self.authority = self.payment.gateway_transaction_id


class SuccessfulCallbackTests(CallbackBase):
    def test_successful_callback_marks_payment_success_and_order_paid(self):
        result = handle_callback(signed_params(self.authority, "ok"))
        self.assertEqual(result.status, Payment.Status.SUCCESS)
        self.assertTrue(result.gateway_ref_id)
        self.assertIsNotNone(result.paid_at)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)

    def test_successful_callback_decrements_stock(self):
        product = self.order.items.first().product
        before = product.stock_quantity
        qty = self.order.items.first().quantity

        handle_callback(signed_params(self.authority, "ok"))

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, before - qty)


class IdempotencyTests(CallbackBase):
    def test_duplicate_callback_does_not_double_decrement_stock(self):
        product = self.order.items.first().product
        before = product.stock_quantity
        qty = self.order.items.first().quantity

        first = handle_callback(signed_params(self.authority, "ok"))
        second = handle_callback(signed_params(self.authority, "ok"))

        self.assertEqual(first.status, Payment.Status.SUCCESS)
        self.assertEqual(second.status, Payment.Status.SUCCESS)
        self.assertEqual(first.pk, second.pk)

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, before - qty, "stock decremented more than once")

    def test_duplicate_callback_keeps_a_single_successful_payment(self):
        handle_callback(signed_params(self.authority, "ok"))
        handle_callback(signed_params(self.authority, "ok"))
        self.assertEqual(Payment.objects.filter(order=self.order, status=Payment.Status.SUCCESS).count(), 1)

    def test_cancelled_attempt_is_terminal_replaying_ok_cannot_flip_it(self):
        """A cancelled attempt stays cancelled even if a validly-signed
        'ok' callback for the same authority arrives later (an old link
        replayed from browser history). Retrying payment means a NEW
        attempt with its own authority."""
        handle_callback(signed_params(self.authority, "cancelled"))
        result = handle_callback(signed_params(self.authority, "ok"))
        self.assertEqual(result.status, Payment.Status.CANCELLED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.UNPAID)

    def test_success_is_terminal_cannot_be_overwritten(self):
        handle_callback(signed_params(self.authority, "ok"))
        # Forged attempt to downgrade/overwrite after success.
        result = handle_callback(signed_params(self.authority, "cancelled"))
        self.assertEqual(result.status, Payment.Status.SUCCESS)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)


class CancelledCallbackTests(CallbackBase):
    def test_cancelled_callback_marks_cancelled_and_order_returns_to_unpaid(self):
        result = handle_callback(signed_params(self.authority, "cancelled"))
        self.assertEqual(result.status, Payment.Status.CANCELLED)
        self.assertIsNone(result.paid_at)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.UNPAID)

    def test_cancelled_callback_does_not_touch_stock(self):
        product = self.order.items.first().product
        before = product.stock_quantity
        handle_callback(signed_params(self.authority, "cancelled"))
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, before)


class FailedCallbackTests(CallbackBase):
    def test_gateway_reported_failure_marks_failed(self):
        # "failed" is a status the gateway can report; the mock signs it
        # but returns a non-success verification.
        result = handle_callback(signed_params(self.authority, "failed"))
        self.assertEqual(result.status, Payment.Status.FAILED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)

    def test_forged_signature_is_rejected(self):
        params = {"authority": self.authority, "status": "ok", "sig": "forged" * 8}
        result = handle_callback(params)
        self.assertEqual(result.status, Payment.Status.FAILED)
        self.assertIn("signature", result.failure_reason.lower())

        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_tampered_status_with_valid_signature_for_other_status_is_rejected(self):
        # Signature computed for "cancelled" but the attacker flips status
        # to "ok" without re-signing.
        params = {"authority": self.authority, "status": "ok", "sig": _sign(self.authority, "cancelled")}
        result = handle_callback(params)
        self.assertEqual(result.status, Payment.Status.FAILED)
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)


class InvalidCallbackTests(CallbackBase):
    def test_unknown_authority_raises(self):
        with self.assertRaises(PaymentError):
            handle_callback(signed_params("nonexistent-authority", "ok"))

    def test_missing_authority_raises(self):
        with self.assertRaises(PaymentError):
            handle_callback({"status": "ok", "sig": "x"})

    def test_authority_of_another_payment_is_rejected_by_signature_check(self):
        other_order = make_unpaid_order(make_user(phone="+989410000099"))
        other = initiate_payment(other_order.user, other_order.pk, callback_url=CALLBACK)["payment"]
        # Attacker tries to confirm THEIR payment using OUR authority id,
        # or vice versa. The signature/authority-match guard rejects it.
        result = handle_callback(
            {"authority": self.authority, "status": "ok", "sig": _sign(other.gateway_transaction_id, "ok")}
        )
        self.assertEqual(result.status, Payment.Status.FAILED)


class AmountMismatchTests(CallbackBase):
    def test_amount_mismatch_prevents_paid_transition(self):
        # Simulate the order total being altered after initiation.
        self.order.total = self.order.total + 50000
        self.order.save(update_fields=["total"])

        result = handle_callback(signed_params(self.authority, "ok"))
        self.assertEqual(result.status, Payment.Status.FAILED)
        self.assertIn("mismatch", result.failure_reason.lower())

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)


class CallbackEndpointTests(CallbackBase):
    """Exercises the actual HTTP callback endpoint (GET + POST, CSRF-exempt)."""

    def test_get_callback_redirects_to_frontend_result(self):
        params = signed_params(self.authority, "ok")
        response = self.client.get(reverse("payment-callback"), params)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("/payment/result/", response["Location"])
        self.assertIn(f"{self.payment.pk}/", response["Location"])

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)

    def test_post_callback_works_without_csrf_token(self):
        # A real client with CSRF enforcement ON -- proves the endpoint's
        # csrf_exempt genuinely covers gateway POSTs, which carry no token.
        from rest_framework.test import APIClient

        csrf_client = APIClient(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("payment-callback"), signed_params(self.authority, "ok")
        )
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)

    def test_unknown_callback_redirects_to_failure_result(self):
        response = self.client.get(
            reverse("payment-callback"), signed_params("nope", "ok")
        )
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=failed", response["Location"])

    def test_root_alias_callback_path_also_works(self):
        params = signed_params(self.authority, "ok")
        response = self.client.get("/payment/callback/", params)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)
