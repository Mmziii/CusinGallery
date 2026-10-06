"""
ZarinPal gateway tests (Phase C - Real payments).

NO test in this module touches the network. The adapter's HTTP layer is
replaced by FakeZarinpalHTTP below, patched over the exact `requests.post`
call site the adapter uses, so everything else is exercised for real:
payload construction (Toman amounts, currency=IRT, sandbox vs production
hosts), response-envelope parsing, the errors/exception split, and the
service layer's full state machine (SUCCESS/FAILED/CANCELLED/PENDING
transitions, exactly-once stock decrement, idempotent + concurrent
callbacks).

The fake dispatches on the URL suffix (request.json vs verify.json) and
records every call, so tests can assert exactly what WOULD have gone to
ZarinPal -- including that verify() sends OUR stored amount and
transaction id, never callback-supplied values.
"""
import threading
from unittest import skipIf

import requests
from django.db import connection, connections
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status as http_status

from apps.core.testing import (
    CacheIsolatedAPITestCase,
    CacheIsolatedAPITransactionTestCase,
)
from apps.orders.models import Order

from ..gateways.base import GatewayError
from ..gateways.zarinpal import (
    API_HOST_PRODUCTION,
    API_HOST_SANDBOX,
    PAY_PAGE_PRODUCTION,
    PAY_PAGE_SANDBOX,
    ZarinpalGateway,
)
from ..models import Payment
from ..services import PaymentError, handle_callback, initiate_payment
from .helpers import make_unpaid_order, make_user

CALLBACK = "http://testserver/api/v1/payments/callback/"
TEST_MERCHANT_ID = "c64a6c77-0000-4000-8000-000000000000"
AUTHORITY = "A0000000000000000000000000000TESTAUTH"
CARD_HASH = "1EBE3EBE35C7EC0F8D6EE4F2F859107A87822CA179BC9528767EA7B5489B69"

ZARINPAL_SETTINGS = dict(
    PAYMENT_GATEWAY="zarinpal",
    PAYMENT_MERCHANT_ID=TEST_MERCHANT_ID,
    PAYMENT_ZARINPAL_SANDBOX=False,
    PAYMENT_GATEWAY_TIMEOUT=5,
)


# ---------------------------------------------------------------------------
# Fake HTTP layer
# ---------------------------------------------------------------------------

def envelope(data=None, errors=None):
    """A ZarinPal v4 response envelope: {"data": {...}|[], "errors": {...}|[]}."""
    return {
        "data": data if data is not None else [],
        "errors": errors if errors is not None else [],
    }


def request_ok(authority=AUTHORITY):
    return envelope({
        "code": 100, "message": "Success", "authority": authority,
        "fee_type": "Merchant", "fee": 0,
    })


def verify_ok(ref_id=123456789, code=100, card_pan="603770******4281", card_hash=CARD_HASH):
    return envelope({
        "code": code, "message": "Verified", "ref_id": ref_id,
        "card_pan": card_pan, "card_hash": card_hash,
        "fee_type": "Merchant", "fee": 0,
    })


def gateway_errors(code=-9, message="The input params invalid, validation error."):
    return envelope(data=[], errors={"code": code, "message": message, "validations": []})


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if self._payload is None:  # simulate a non-JSON body
            raise ValueError("No JSON could be decoded")
        return self._payload


class FakeZarinpalHTTP:
    """
    Context manager replacing `requests.post` for the zarinpal module.

    Configure what the "network" does per endpoint:
        request_response / request_exception  -> payment request.json
        verify_response  / verify_exception   -> payment verify.json
    A call with no configured behaviour fails the test loudly -- tests
    declare exactly which HTTP interactions they expect (e.g. a NOK
    callback must NOT trigger a verify call).
    """

    def __init__(self, request_response=None, verify_response=None,
                 request_exception=None, verify_exception=None):
        self.request_response = request_response
        self.verify_response = verify_response
        self.request_exception = request_exception
        self.verify_exception = verify_exception
        self.calls = []  # every call as (url, payload)

    # -- assertions helpers --------------------------------------------------

    @property
    def request_calls(self):
        return [c for c in self.calls if c[0].endswith("request.json")]

    @property
    def verify_calls(self):
        return [c for c in self.calls if c[0].endswith("verify.json")]

    # -- the patched function ------------------------------------------------

    def _post(self, url, json=None, timeout=None, headers=None):
        self.calls.append((url, json))
        if url.endswith("request.json"):
            if self.request_exception is not None:
                raise self.request_exception
            if self.request_response is None:
                raise AssertionError(f"Unexpected ZarinPal payment request call to {url}")
            return FakeResponse(*self.request_response) \
                if isinstance(self.request_response, tuple) else FakeResponse(self.request_response)
        if url.endswith("verify.json"):
            if self.verify_exception is not None:
                raise self.verify_exception
            if self.verify_response is None:
                raise AssertionError(f"Unexpected ZarinPal verify call to {url}")
            return FakeResponse(*self.verify_response) \
                if isinstance(self.verify_response, tuple) else FakeResponse(self.verify_response)
        raise AssertionError(f"Unexpected URL requested: {url}")

    def __enter__(self):
        from unittest import mock

        self._patcher = mock.patch(
            "apps.payments.gateways.zarinpal.requests.post", side_effect=self._post
        )
        self._patcher.start()
        return self

    def __exit__(self, *exc_info):
        self._patcher.stop()
        return False


# ---------------------------------------------------------------------------
# Adapter-level tests (initiate)
# ---------------------------------------------------------------------------

class AdapterTestBase(CacheIsolatedAPITestCase):
    def make_payment(self, amount=None):
        user = make_user()
        order = make_unpaid_order(user)
        return Payment.objects.create(
            order=order,
            amount=amount if amount is not None else order.total,
            gateway="zarinpal",
        )


@override_settings(**ZARINPAL_SETTINGS)
class ZarinpalInitiateTests(AdapterTestBase):
    def test_initiate_sends_toman_request_and_returns_startpay_redirect(self):
        payment = self.make_payment()
        order = payment.order
        with FakeZarinpalHTTP(request_response=request_ok()) as fake:
            result = ZarinpalGateway().initiate(payment, CALLBACK)

        url, payload = fake.request_calls[0]
        self.assertEqual(url, f"{API_HOST_PRODUCTION}/pg/v4/payment/request.json")
        self.assertEqual(payload["merchant_id"], TEST_MERCHANT_ID)
        # Whole Toman, sent unchanged with currency=IRT -- no 10x Rial
        # conversion anywhere.
        self.assertEqual(payload["amount"], order.total)
        self.assertEqual(payload["currency"], "IRT")
        self.assertEqual(payload["callback_url"], CALLBACK)
        self.assertIn(order.order_number, payload["description"])
        self.assertEqual(payload["metadata"]["order_id"], order.order_number)

        self.assertEqual(result.gateway_transaction_id, AUTHORITY)
        self.assertEqual(result.redirect_url, f"{PAY_PAGE_PRODUCTION}{AUTHORITY}")
        # The merchant id is server-side only and must never ride along
        # in the customer-visible redirect URL.
        self.assertNotIn(TEST_MERCHANT_ID, result.redirect_url)

    def test_sandbox_mode_switches_only_the_hosts(self):
        payment = self.make_payment()
        with self.settings(PAYMENT_ZARINPAL_SANDBOX=True):
            with FakeZarinpalHTTP(request_response=request_ok()) as fake:
                result = ZarinpalGateway().initiate(payment, CALLBACK)

        url, _ = fake.request_calls[0]
        self.assertEqual(url, f"{API_HOST_SANDBOX}/pg/v4/payment/request.json")
        self.assertEqual(result.redirect_url, f"{PAY_PAGE_SANDBOX}{AUTHORITY}")

    def test_gateway_refusal_is_a_gateway_error(self):
        payment = self.make_payment()
        with FakeZarinpalHTTP(request_response=gateway_errors(code=-9)):
            with self.assertRaises(GatewayError) as ctx:
                ZarinpalGateway().initiate(payment, CALLBACK)
        self.assertIn("-9", str(ctx.exception))

    def test_network_timeout_is_a_gateway_error(self):
        payment = self.make_payment()
        with FakeZarinpalHTTP(request_exception=requests.exceptions.ConnectTimeout()):
            with self.assertRaises(GatewayError):
                ZarinpalGateway().initiate(payment, CALLBACK)

    def test_http_500_is_a_gateway_error(self):
        payment = self.make_payment()
        with FakeZarinpalHTTP(request_response=({}, 500)):
            with self.assertRaises(GatewayError) as ctx:
                ZarinpalGateway().initiate(payment, CALLBACK)
        self.assertIn("500", str(ctx.exception))

    def test_non_json_body_is_a_gateway_error(self):
        payment = self.make_payment()
        with FakeZarinpalHTTP(request_response=(None, 200)):
            with self.assertRaises(GatewayError):
                ZarinpalGateway().initiate(payment, CALLBACK)

    def test_missing_authority_in_accepted_response_is_a_gateway_error(self):
        payment = self.make_payment()
        with FakeZarinpalHTTP(request_response=envelope({"code": 100, "message": "Success"})):
            with self.assertRaises(GatewayError):
                ZarinpalGateway().initiate(payment, CALLBACK)

    def test_missing_merchant_id_is_a_gateway_error(self):
        payment = self.make_payment()
        with self.settings(PAYMENT_MERCHANT_ID=""):
            with FakeZarinpalHTTP(request_response=request_ok()):
                with self.assertRaises(GatewayError) as ctx:
                    ZarinpalGateway().initiate(payment, CALLBACK)
        self.assertIn("PAYMENT_MERCHANT_ID", str(ctx.exception))

    def test_missing_callback_url_is_a_gateway_error(self):
        payment = self.make_payment()
        with FakeZarinpalHTTP(request_response=request_ok()):
            with self.assertRaises(GatewayError):
                ZarinpalGateway().initiate(payment, "")


# ---------------------------------------------------------------------------
# Adapter-level tests (verify)
# ---------------------------------------------------------------------------

@override_settings(**ZARINPAL_SETTINGS)
class ZarinpalVerifyTests(AdapterTestBase):
    def test_status_nok_is_cancelled_without_any_verify_call(self):
        """ZarinPal instructs merchants NOT to call verify for NOK; the
        adapter must honor that and report the customer-cancel outcome."""
        payment = self.make_payment()
        payment.gateway_transaction_id = AUTHORITY
        payment.save(update_fields=["gateway_transaction_id"])

        with FakeZarinpalHTTP() as fake:  # nothing configured: ANY call fails the test
            result = ZarinpalGateway().verify(
                payment, {"Authority": AUTHORITY, "Status": "NOK"}
            )

        self.assertFalse(result.success)
        self.assertTrue(result.cancelled)
        self.assertEqual(fake.calls, [])

    def test_status_ok_verifies_server_side_and_maps_receipt_data(self):
        payment = self.make_payment()
        payment.gateway_transaction_id = AUTHORITY
        payment.save(update_fields=["gateway_transaction_id"])

        with FakeZarinpalHTTP(verify_response=verify_ok()) as fake:
            result = ZarinpalGateway().verify(
                payment, {"Authority": AUTHORITY, "Status": "OK"}
            )

        url, payload = fake.verify_calls[0]
        self.assertEqual(url, f"{API_HOST_PRODUCTION}/pg/v4/payment/verify.json")
        # verify sends OUR stored snapshot values, never callback values:
        self.assertEqual(payload["merchant_id"], TEST_MERCHANT_ID)
        self.assertEqual(payload["amount"], payment.amount)
        self.assertEqual(payload["currency"], "IRT")
        self.assertEqual(payload["authority"], AUTHORITY)

        self.assertTrue(result.success)
        self.assertEqual(result.gateway_ref_id, "123456789")
        self.assertEqual(result.card_pan, "603770******4281")
        self.assertEqual(result.card_fingerprint, CARD_HASH)

    def test_code_101_repeat_verify_is_still_success(self):
        """Per ZarinPal's docs, verify returns 101 (not 100) when the
        transaction was already verified once -- it is still a captured
        payment, and honoring it is what makes replayed callbacks and
        lost verify responses resolve correctly."""
        payment = self.make_payment()
        payment.gateway_transaction_id = AUTHORITY
        payment.save(update_fields=["gateway_transaction_id"])

        with FakeZarinpalHTTP(verify_response=verify_ok(ref_id=42, code=101)):
            result = ZarinpalGateway().verify(
                payment, {"Authority": AUTHORITY, "Status": "OK"}
            )
        self.assertTrue(result.success)
        self.assertEqual(result.gateway_ref_id, "42")

    def test_verify_business_refusal_is_a_failed_result_not_an_exception(self):
        payment = self.make_payment()
        payment.gateway_transaction_id = AUTHORITY
        payment.save(update_fields=["gateway_transaction_id"])

        with FakeZarinpalHTTP(verify_response=gateway_errors(code=-50, message="payment request not found")):
            result = ZarinpalGateway().verify(
                payment, {"Authority": AUTHORITY, "Status": "OK"}
            )
        self.assertFalse(result.success)
        self.assertFalse(result.cancelled)
        self.assertIn("payment request not found", result.failure_reason)

    def test_verify_network_error_raises_gateway_error(self):
        """Unreachable gateway during verify is NOT a payment outcome --
        the service layer must keep the attempt PENDING (money state
        unknown), which is only possible if this raises."""
        payment = self.make_payment()
        payment.gateway_transaction_id = AUTHORITY
        payment.save(update_fields=["gateway_transaction_id"])

        with FakeZarinpalHTTP(verify_exception=requests.exceptions.ReadTimeout()):
            with self.assertRaises(GatewayError):
                ZarinpalGateway().verify(payment, {"Authority": AUTHORITY, "Status": "OK"})

    def test_callback_authority_mismatch_is_rejected(self):
        payment = self.make_payment()
        payment.gateway_transaction_id = AUTHORITY
        payment.save(update_fields=["gateway_transaction_id"])

        with FakeZarinpalHTTP() as fake:  # no verify call may happen
            result = ZarinpalGateway().verify(
                payment, {"Authority": "SOME-OTHER-AUTHORITY", "Status": "OK"}
            )
        self.assertFalse(result.success)
        self.assertIn("does not match", result.failure_reason)
        self.assertEqual(fake.calls, [])

    def test_missing_status_is_rejected(self):
        payment = self.make_payment()
        payment.gateway_transaction_id = AUTHORITY
        payment.save(update_fields=["gateway_transaction_id"])

        with FakeZarinpalHTTP() as fake:
            result = ZarinpalGateway().verify(payment, {"Authority": AUTHORITY})
        self.assertFalse(result.success)
        self.assertIn("Status", result.failure_reason)
        self.assertEqual(fake.calls, [])

    def test_sandbox_verify_uses_sandbox_host(self):
        payment = self.make_payment()
        payment.gateway_transaction_id = AUTHORITY
        payment.save(update_fields=["gateway_transaction_id"])

        with self.settings(PAYMENT_ZARINPAL_SANDBOX=True):
            with FakeZarinpalHTTP(verify_response=verify_ok()) as fake:
                ZarinpalGateway().verify(payment, {"Authority": AUTHORITY, "Status": "OK"})
        self.assertEqual(fake.verify_calls[0][0], f"{API_HOST_SANDBOX}/pg/v4/payment/verify.json")


# ---------------------------------------------------------------------------
# Service-level flow tests through the REAL handle_callback / initiate_payment
# ---------------------------------------------------------------------------

@override_settings(**ZARINPAL_SETTINGS)
class ZarinpalServiceFlowTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989430000010")
        self.order = make_unpaid_order(self.user)
        self.product = self.order.items.first().product
        self.quantity = self.order.items.first().quantity

    def _initiate(self):
        return initiate_payment(self.user, self.order.pk, callback_url=CALLBACK)["payment"]

    def test_successful_flow_pays_order_decrements_stock_once_stores_receipt(self):
        stock_before = self.product.stock_quantity
        with FakeZarinpalHTTP(request_response=request_ok(), verify_response=verify_ok()) as fake:
            payment = self._initiate()
            self.assertEqual(payment.gateway, "zarinpal")
            self.assertEqual(payment.gateway_transaction_id, AUTHORITY)

            result = handle_callback({"Authority": AUTHORITY, "Status": "OK"})

        self.assertEqual(result.status, Payment.Status.SUCCESS)
        self.assertEqual(result.gateway_ref_id, "123456789")
        self.assertEqual(result.card_pan, "603770******4281")
        self.assertEqual(result.card_pan_hash, CARD_HASH)
        self.assertIsNotNone(result.paid_at)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, stock_before - self.quantity)
        self.assertEqual(len(fake.verify_calls), 1)

    def test_user_cancelled_at_gateway_page(self):
        stock_before = self.product.stock_quantity
        with FakeZarinpalHTTP(request_response=request_ok()) as fake:
            self._initiate()
            result = handle_callback({"Authority": AUTHORITY, "Status": "NOK"})

        self.assertEqual(result.status, Payment.Status.CANCELLED)
        self.assertIsNone(result.paid_at)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.UNPAID)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, stock_before)
        self.assertEqual(fake.verify_calls, [])

    def test_failed_verification_marks_payment_and_order_failed(self):
        with FakeZarinpalHTTP(request_response=request_ok(),
                              verify_response=gateway_errors(code=-50, message="payment request not found")):
            self._initiate()
            result = handle_callback({"Authority": AUTHORITY, "Status": "OK"})

        self.assertEqual(result.status, Payment.Status.FAILED)
        self.assertIn("payment request not found", result.failure_reason)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)

    def test_amount_mismatch_refuses_to_mark_paid_even_when_gateway_says_ok(self):
        """The gateway verified the money for the ORIGINAL amount, but the
        order total no longer matches the payment snapshot -- the service
        must refuse the paid transition regardless of the gateway answer."""
        with FakeZarinpalHTTP(request_response=request_ok(), verify_response=verify_ok()) as fake:
            payment = self._initiate()
            self.order.total = self.order.total + 50000
            self.order.save(update_fields=["total"])

            result = handle_callback({"Authority": AUTHORITY, "Status": "OK"})

        self.assertEqual(result.status, Payment.Status.FAILED)
        self.assertIn("mismatch", result.failure_reason.lower())
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        # The verify call still went out with the frozen snapshot amount.
        self.assertEqual(fake.verify_calls[0][1]["amount"], payment.amount)

    def test_replayed_callback_verifies_once_and_decrements_stock_once(self):
        stock_before = self.product.stock_quantity
        with FakeZarinpalHTTP(request_response=request_ok(), verify_response=verify_ok()) as fake:
            self._initiate()
            first = handle_callback({"Authority": AUTHORITY, "Status": "OK"})
            second = handle_callback({"Authority": AUTHORITY, "Status": "OK"})

        self.assertEqual(first.status, Payment.Status.SUCCESS)
        self.assertEqual(second.status, Payment.Status.SUCCESS)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.filter(order=self.order, status=Payment.Status.SUCCESS).count(), 1)
        # The replay never reaches the gateway: the terminal-state fast
        # path short-circuits it.
        self.assertEqual(len(fake.verify_calls), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, stock_before - self.quantity)

    def test_verify_timeout_keeps_attempt_pending_then_replay_completes_it(self):
        fake = FakeZarinpalHTTP(
            request_response=request_ok(),
            verify_exception=requests.exceptions.ReadTimeout(),
        )
        # The WHOLE test runs inside one patched-HTTP context: the replay
        # after "recovery" must also hit the fake, never the network.
        with fake:
            self._initiate()
            result = handle_callback({"Authority": AUTHORITY, "Status": "OK"})

            self.assertEqual(result.status, Payment.Status.PENDING)
            self.order.refresh_from_db()
            self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
            self.product.refresh_from_db()
            self.assertEqual(self.product.stock_quantity, 10)

            # Network recovers; ZarinPal answers the repeat verify with
            # its documented code 101 ("already verified") -- the
            # replayed callback must complete the payment now.
            fake.verify_exception = None
            fake.verify_response = verify_ok(ref_id=777, code=101)
            result = handle_callback({"Authority": AUTHORITY, "Status": "OK"})

        self.assertEqual(result.status, Payment.Status.SUCCESS)
        self.assertEqual(result.gateway_ref_id, "777")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10 - self.quantity)

    def test_initiate_with_unreachable_gateway_records_failure_and_returns_502(self):
        with FakeZarinpalHTTP(request_exception=requests.exceptions.ConnectTimeout()):
            with self.assertRaises(PaymentError) as ctx:
                self._initiate()
        self.assertEqual(ctx.exception.http_status, http_status.HTTP_502_BAD_GATEWAY)

        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.UNPAID)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)

    def test_initiate_endpoint_returns_zarinpal_redirect_url(self):
        self.client.login(username="+989430000010", password="a-strong-passw0rd!")
        with FakeZarinpalHTTP(request_response=request_ok()):
            response = self.client.post(
                reverse("payment-initiate"), {"order_id": self.order.pk}, format="json"
            )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data["redirect_url"], f"{PAY_PAGE_PRODUCTION}{AUTHORITY}")

    def test_http_callback_with_zarinpal_query_params_redirects_to_success_result(self):
        with FakeZarinpalHTTP(request_response=request_ok(), verify_response=verify_ok()):
            self._initiate()
            response = self.client.get(
                reverse("payment-callback"), {"Authority": AUTHORITY, "Status": "OK"}
            )
        self.assertEqual(response.status_code, http_status.HTTP_302_FOUND)
        self.assertIn("status=success", response["Location"])
        payment = Payment.objects.get(order=self.order, status=Payment.Status.SUCCESS)
        self.assertEqual(payment.gateway_ref_id, "123456789")

    def test_http_callback_with_verify_timeout_redirects_to_pending_result(self):
        with FakeZarinpalHTTP(request_response=request_ok(),
                              verify_exception=requests.exceptions.ReadTimeout()):
            self._initiate()
            response = self.client.get(
                reverse("payment-callback"), {"Authority": AUTHORITY, "Status": "OK"}
            )
        self.assertEqual(response.status_code, http_status.HTTP_302_FOUND)
        self.assertIn("status=pending", response["Location"])

    def test_http_callback_with_nok_redirects_to_cancelled_result(self):
        with FakeZarinpalHTTP(request_response=request_ok()):
            self._initiate()
            response = self.client.get(
                reverse("payment-callback"), {"Authority": AUTHORITY, "Status": "NOK"}
            )
        self.assertEqual(response.status_code, http_status.HTTP_302_FOUND)
        self.assertIn("status=cancelled", response["Location"])


@skipIf(
    connection.vendor == "sqlite",
    "SQLite locks the entire database file while any write transaction "
    "is open, so two threads racing through the callback flow hit "
    "'database table is locked' errors that PostgreSQL's row-level "
    "locking (which production uses, and which this test is meant to "
    "exercise) never produces. Run against PostgreSQL instead.",
)
@override_settings(**ZARINPAL_SETTINGS)
class ConcurrentZarinpalCallbackTests(CacheIsolatedAPITransactionTestCase):
    """Two ZarinPal callbacks for the same attempt arriving at the same
    instant (double-click, browser retry, gateway re-notification) must
    pay the order and decrement stock exactly once."""

    def test_simultaneous_callbacks_pay_exactly_once(self):
        user = make_user(phone="+989430000030")
        order = make_unpaid_order(user)
        product = order.items.first().product
        stock_before = product.stock_quantity
        quantity = order.items.first().quantity

        with FakeZarinpalHTTP(request_response=request_ok(), verify_response=verify_ok()):
            payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]
            params = {"Authority": payment.gateway_transaction_id, "Status": "OK"}

            results = []
            barrier = threading.Barrier(2)

            def fire():
                try:
                    barrier.wait(timeout=10)
                    response = Client().get(reverse("payment-callback"), params)
                    results.append(response.status_code)
                finally:
                    connections.close_all()

            threads = [threading.Thread(target=fire) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        self.assertEqual(sorted(results), [http_status.HTTP_302_FOUND, http_status.HTTP_302_FOUND])
        self.assertEqual(
            Payment.objects.filter(order=order, status=Payment.Status.SUCCESS).count(), 1
        )
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, stock_before - quantity)


# ---------------------------------------------------------------------------
# Gateway selection (env -> registry)
# ---------------------------------------------------------------------------

class GatewayRegistryTests(SimpleTestCase):
    def test_empty_setting_selects_mock_for_development(self):
        from ..gateways import MockGateway, get_gateway

        with override_settings(PAYMENT_GATEWAY=""):
            self.assertIsInstance(get_gateway(), MockGateway)

    def test_mock_is_selectable_explicitly(self):
        from ..gateways import MockGateway, get_gateway

        with override_settings(PAYMENT_GATEWAY="mock"):
            self.assertIsInstance(get_gateway(), MockGateway)

    def test_zarinpal_is_selectable(self):
        from ..gateways import get_gateway

        with override_settings(PAYMENT_GATEWAY="zarinpal"):
            self.assertIsInstance(get_gateway(), ZarinpalGateway)

    def test_selection_ignores_case_and_whitespace(self):
        from ..gateways import get_gateway

        with override_settings(PAYMENT_GATEWAY="  ZarinPal "):
            self.assertIsInstance(get_gateway(), ZarinpalGateway)

    def test_unknown_gateway_fails_loudly_with_instructions(self):
        from django.core.exceptions import ImproperlyConfigured

        from ..gateways import get_gateway

        with override_settings(PAYMENT_GATEWAY="idpay"):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                get_gateway()
        self.assertIn("zarinpal", str(ctx.exception))
