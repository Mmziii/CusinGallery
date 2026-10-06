"""
Refund tracking tests (Phase C - Real payments).

Covers the whole refund ledger with REAL flows: paid orders are paid
through the actual payment initiate/callback path (mock gateway, real
signatures), cancellations/returns go through apps/orders/workflow.py,
and the admin tests drive OrderAdmin.save_model / the changelist exactly
like the owner's browser does. The rules under test:

* cancelling or returning a PAID order flags it refund-required with the
  full total, once (terminal statuses make repeats no-ops);
* cancelling an UNPAID order never touches the refund ledger (no money
  moved) -- mirroring how it never touches stock;
* money the gateway verified but the order can no longer receive (late
  capture after auto-cancel, duplicate second capture) is recorded and
  flagged instead of vanishing;
* marking refunded REQUIRES an added note, stamps refunded_at, and moves
  a PAID payment_status to REFUNDED; invalid ledger moves persist nothing.
"""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings

from apps.core.testing import CacheIsolatedAPITestCase
from apps.orders.admin import OrderAdmin
from apps.orders.models import Order
from apps.orders.refunds import RefundError, flag_refund_required, mark_refunded
from apps.orders.workflow import set_status
from apps.payments.gateways.mock import _sign
from apps.payments.models import Payment
from apps.payments.services import handle_callback, initiate_payment
from apps.payments.tests.helpers import make_product, make_unpaid_order, make_user
from apps.products.models import Product

CALLBACK = "http://testserver/api/v1/payments/callback/"

# Rendering admin HTML pages in tests needs the plain (non-manifest)
# staticfiles storage -- same pattern as apps/banners/tests/test_admin_banners.py.
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


def signed_ok(authority):
    return {"authority": authority, "status": "ok", "sig": _sign(authority, "ok")}


class RefundTestBase(CacheIsolatedAPITestCase):
    def make_paid_order(self, stock=10, quantity=2, price=100000):
        """A REAL paid order: checkout -> initiate -> signed success
        callback (stock already decremented by the real payment path)."""
        self.user = make_user()
        self.product = make_product(stock_quantity=stock, price=price)
        order = make_unpaid_order(self.user, product=self.product, quantity=quantity)
        payment = initiate_payment(self.user, order.pk, callback_url=CALLBACK)["payment"]
        handle_callback(signed_ok(payment.gateway_transaction_id))
        order.refresh_from_db()
        self.product.refresh_from_db()
        return order

    def return_paid_order(self, order):
        """Walk a paid (confirmed) order to RETURNED through the real DAG:
        confirmed -> processing -> shipped (with tracking code) -> returned."""
        set_status(order, Order.Status.PROCESSING)
        order.refresh_from_db()
        order.tracking_code = "POST-REFUND-1"
        order.save(update_fields=["tracking_code"])
        set_status(order, Order.Status.SHIPPED)
        order.refresh_from_db()
        return set_status(order, Order.Status.RETURNED)


class CancelRefundFlagTests(RefundTestBase):
    def test_cancelling_paid_order_flags_refund_required_with_full_total(self):
        order = self.make_paid_order()
        self.assertEqual(order.refund_status, Order.RefundStatus.NONE)

        cancelled = set_status(order, Order.Status.CANCELLED)

        self.assertEqual(cancelled.status, Order.Status.CANCELLED)
        self.assertEqual(cancelled.refund_status, Order.RefundStatus.REQUIRED)
        self.assertEqual(cancelled.refund_amount, order.total)
        self.assertIn("لغو", cancelled.refund_reference)
        self.assertIsNone(cancelled.refunded_at)
        # Stock side is unchanged from Phase B: restored exactly once.
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertIsNotNone(cancelled.stock_restored_at)

    def test_repeated_cancel_does_not_double_the_refund_amount(self):
        order = self.make_paid_order()
        set_status(order, Order.Status.CANCELLED)
        again = set_status(order, Order.Status.CANCELLED)  # idempotent no-op
        self.assertEqual(again.refund_amount, order.total)
        self.assertEqual(again.refund_reference.count("لغو"), 1)

    def test_cancelling_unpaid_order_does_not_touch_refund_ledger(self):
        user = make_user()
        order = make_unpaid_order(user)
        cancelled = set_status(order, Order.Status.CANCELLED)
        self.assertEqual(cancelled.refund_status, Order.RefundStatus.NONE)
        self.assertEqual(cancelled.refund_amount, 0)
        self.assertEqual(cancelled.refund_reference, "")

    def test_returning_paid_order_flags_refund_required(self):
        order = self.make_paid_order()
        returned = self.return_paid_order(order)
        self.assertEqual(returned.status, Order.Status.RETURNED)
        self.assertEqual(returned.refund_status, Order.RefundStatus.REQUIRED)
        self.assertEqual(returned.refund_amount, order.total)
        self.assertIn("مرجوع", returned.refund_reference)
        # A return does NOT restore stock (goods come back physically);
        # only the money side is flagged here.
        self.assertIsNone(returned.stock_restored_at)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)


class RefundLedgerMechanismTests(RefundTestBase):
    def test_flags_accumulate_with_journal_lines(self):
        order = self.make_paid_order()
        flag_refund_required(order, 50000, note="رویداد اول")
        flag_refund_required(order, 30000, note="رویداد دوم")
        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)
        self.assertEqual(order.refund_amount, 80000)
        self.assertIn("رویداد اول", order.refund_reference)
        self.assertIn("رویداد دوم", order.refund_reference)

    def test_non_positive_amount_is_ignored(self):
        order = self.make_paid_order()
        flag_refund_required(order, 0, note="باگ")
        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.NONE)
        self.assertEqual(order.refund_amount, 0)

    def test_mark_refunded_requires_a_note(self):
        order = self.make_paid_order()
        set_status(order, Order.Status.CANCELLED)
        order.refresh_from_db()  # pick up the system's refund flag
        with self.assertRaises(RefundError):
            mark_refunded(order, "   ")
        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)
        self.assertIsNone(order.refunded_at)

    def test_mark_refunded_on_unflagged_order_raises(self):
        order = self.make_paid_order()
        with self.assertRaises(RefundError):
            mark_refunded(order, "کد بازپرداخت: ۱۲۳")
        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.NONE)

    def test_mark_refunded_completes_the_ledger(self):
        order = self.make_paid_order()
        set_status(order, Order.Status.CANCELLED)
        order.refresh_from_db()

        mark_refunded(order, "بازپرداخت در پنل زرین‌پال، کد رهگیری ۹۸۷۶۵")

        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.REFUNDED)
        self.assertEqual(order.refund_amount, order.total)
        self.assertIsNotNone(order.refunded_at)
        # The journal keeps BOTH the system's flag note and the owner's.
        self.assertIn("لغو", order.refund_reference)
        self.assertIn("۹۸۷۶۵", order.refund_reference)
        # payment_status tells the money story: paid -> refunded.
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)

    def test_mark_refunded_accepts_a_corrected_amount(self):
        order = self.make_paid_order()
        set_status(order, Order.Status.CANCELLED)
        order.refresh_from_db()
        mark_refunded(order, "بازپرداخت جزئی پس از هماهنگی", amount=order.total - 20000)
        order.refresh_from_db()
        self.assertEqual(order.refund_amount, order.total - 20000)


class VerifiedButUnappliedCaptureTests(RefundTestBase):
    """Gateway-verified money that the order can no longer receive must
    be RECORDED and flagged -- never silently dropped, never fulfilled."""

    def test_late_capture_on_cancelled_order_records_money_and_flags_refund(self):
        user = make_user()
        product = make_product(stock_quantity=10)
        order = make_unpaid_order(user, product=product)
        payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]

        # The expiry job (or the owner) cancels the still-unpaid order...
        set_status(order, Order.Status.CANCELLED)
        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.NONE)

        # ...and THEN the customer's completed payment verifies.
        result = handle_callback(signed_ok(payment.gateway_transaction_id))

        self.assertEqual(result.status, Payment.Status.SUCCESS)
        self.assertIsNotNone(result.paid_at)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)  # not fulfilled
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)  # but paid
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)
        self.assertEqual(order.refund_amount, payment.amount)
        self.assertIn("لغو/مرجوعی", order.refund_reference)
        # No stock movement: the order never ships.
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 10)
        self.assertIsNone(order.stock_restored_at)

        # A replayed callback changes nothing.
        replay = handle_callback(signed_ok(payment.gateway_transaction_id))
        self.assertEqual(replay.status, Payment.Status.SUCCESS)
        order.refresh_from_db()
        self.assertEqual(order.refund_amount, payment.amount)

    def test_duplicate_capture_flags_the_second_amount_for_refund(self):
        user = make_user()
        product = make_product(stock_quantity=10)
        order = make_unpaid_order(user, product=product, quantity=2)
        first = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]
        second = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]

        handle_callback(signed_ok(first.gateway_transaction_id))
        loser = handle_callback(signed_ok(second.gateway_transaction_id))

        self.assertEqual(loser.status, Payment.Status.FAILED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        # The customer was charged twice: the duplicate is real money owed
        # back and must show in the refund ledger.
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)
        self.assertEqual(order.refund_amount, second.amount)
        self.assertIn("پرداخت تکراری", order.refund_reference)
        # Fulfilment side untouched: stock decremented exactly once.
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 8)


class OrderAdminRefundTests(RefundTestBase):
    """Drives OrderAdmin.save_model and the changelist -- the exact code
    paths the owner's browser hits (same pattern as test_workflow.py)."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.superuser = get_user_model().objects.create_superuser(
            username="refund-admin", password="x", phone="+989000000002"
        )
        self.model_admin = OrderAdmin(Order, AdminSite())

    def _make_request(self, url="/admin/orders/order/1/change/"):
        request = self.factory.post(url)
        request.user = self.superuser
        from django.contrib.messages.storage.fallback import FallbackStorage

        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _flagged_order(self):
        order = self.make_paid_order()
        set_status(order, Order.Status.CANCELLED)
        order.refresh_from_db()
        return order

    def test_admin_cannot_mark_refunded_without_adding_a_note(self):
        order = self._flagged_order()
        order.refund_status = Order.RefundStatus.REFUNDED  # note unchanged
        request = self._make_request()

        with self.assertRaises(ValidationError):
            self.model_admin.save_model(request, order, None, change=True)

        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)
        self.assertIsNone(order.refunded_at)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_admin_marks_refunded_with_note(self):
        order = self._flagged_order()
        order.refund_status = Order.RefundStatus.REFUNDED
        order.refund_reference = order.refund_reference + "\nکد بازپرداخت پنل: ZP-554433"
        request = self._make_request()

        self.model_admin.save_model(request, order, None, change=True)

        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.REFUNDED)
        self.assertIsNotNone(order.refunded_at)
        self.assertIn("ZP-554433", order.refund_reference)
        self.assertIn("لغو", order.refund_reference)  # journal kept
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)

    def test_admin_can_manually_flag_refund_required_defaults_to_total(self):
        order = self.make_paid_order()
        self.assertEqual(order.refund_status, Order.RefundStatus.NONE)
        order.refund_status = Order.RefundStatus.REQUIRED
        order.refund_amount = 0
        order.refund_reference = "توافق تلفنی با مشتری برای بازپرداخت هزینهٔ ارسال"
        request = self._make_request()

        self.model_admin.save_model(request, order, None, change=True)

        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)
        self.assertEqual(order.refund_amount, order.total)

    def test_admin_cannot_clear_refund_state(self):
        order = self._flagged_order()
        order.refund_status = Order.RefundStatus.NONE
        with self.assertRaises(ValidationError):
            self.model_admin.save_model(self._make_request(), order, None, change=True)
        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)

    def test_admin_cannot_reopen_a_completed_refund(self):
        order = self._flagged_order()
        order.refund_status = Order.RefundStatus.REFUNDED
        order.refund_reference += "\nکد ۱"
        self.model_admin.save_model(self._make_request(), order, None, change=True)
        order.refresh_from_db()

        order.refund_status = Order.RefundStatus.REQUIRED
        with self.assertRaises(ValidationError):
            self.model_admin.save_model(self._make_request(), order, None, change=True)
        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.REFUNDED)

    def test_invalid_refund_move_persists_nothing_even_with_valid_other_edits(self):
        order = self.make_paid_order()
        order.refund_status = Order.RefundStatus.REFUNDED  # nothing flagged -> invalid
        order.tracking_code = "SHOULD-NOT-SAVE"
        with self.assertRaises(ValidationError):
            self.model_admin.save_model(self._make_request(), order, None, change=True)
        order.refresh_from_db()
        self.assertEqual(order.tracking_code, "")
        self.assertEqual(order.refund_status, Order.RefundStatus.NONE)

    def test_refund_badge_column(self):
        order = self.make_paid_order()
        self.assertEqual(self.model_admin.refund_badge(order), "")
        set_status(order, Order.Status.CANCELLED)
        order.refresh_from_db()
        self.assertIn("نیازمند بازپرداخت", self.model_admin.refund_badge(order))
        mark_refunded(order, "کد ۱")
        order.refresh_from_db()
        self.assertIn("بازپرداخت شده", self.model_admin.refund_badge(order))

    @override_settings(**PLAIN_STATIC)
    def test_changelist_filters_orders_needing_a_refund(self):
        flagged = self._flagged_order()
        clean = self.make_paid_order()
        self.client.force_login(self.superuser)

        response = self.client.get("/admin/orders/order/", {"refund_status": "required"})

        self.assertEqual(response.status_code, 200)
        listed = list(response.context["cl"].queryset)
        self.assertEqual([o.pk for o in listed], [flagged.pk])
        self.assertNotIn(clean.pk, [o.pk for o in listed])

    def test_csv_export_includes_refund_columns(self):
        order = self._flagged_order()
        request = self._make_request(url="/admin/orders/order/")
        response = self.model_admin.export_orders_csv(request, Order.objects.filter(pk=order.pk))
        body = response.content.decode("utf-8-sig")
        self.assertIn("refund_status", body)
        self.assertIn("required", body)
        self.assertIn(str(order.refund_amount), body)
