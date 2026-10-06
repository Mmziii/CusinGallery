"""
expire_unpaid_orders command tests (Phase C - Real payments).

The command is cron-facing infrastructure, so the properties that matter
are tested as exactly that: what it cancels, what it must NEVER touch
(paid orders, fresh orders, terminal orders), that stock does not move
(unpaid orders never reserved any), that repeated runs are idempotent,
and that the mid-run race (an order paid between selection and cancel)
loses safely. Orders are backdated with queryset .update() because
created_at is auto_now_add -- the same way an ops script would prepare
fixture data.
"""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.core.testing import CacheIsolatedAPITestCase
from apps.orders.management.commands.expire_unpaid_orders import Command
from apps.orders.models import Order
from apps.payments.gateways.mock import _sign
from apps.payments.models import Payment
from apps.payments.services import handle_callback, initiate_payment
from apps.payments.tests.helpers import make_product, make_unpaid_order, make_user

CALLBACK = "http://testserver/api/v1/payments/callback/"


def backdate(order, hours):
    """Move created_at into the past (auto_now_add fields cannot be set
    through normal saves; .update() is the standard way)."""
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=hours))
    order.refresh_from_db()
    return order


def pay_order(user, order):
    """Pay an order through the REAL initiate/callback flow (mock gateway)."""
    payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]
    handle_callback({
        "authority": payment.gateway_transaction_id,
        "status": "ok",
        "sig": _sign(payment.gateway_transaction_id, "ok"),
    })
    order.refresh_from_db()
    return payment


class ExpireUnpaidOrdersTests(CacheIsolatedAPITestCase):
    def run_command(self, **kwargs):
        out = StringIO()
        call_command("expire_unpaid_orders", stdout=out, **kwargs)
        return out.getvalue()

    def test_old_unpaid_order_is_cancelled(self):
        user = make_user()
        order = make_unpaid_order(user)
        backdate(order, 30)

        output = self.run_command()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIn(order.order_number, output)
        self.assertIn("cancelled 1", output)

    def test_fresh_unpaid_order_is_left_alone(self):
        user = make_user()
        order = make_unpaid_order(user)  # created now
        backdate(order, 2)  # younger than the 24h default

        output = self.run_command()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertIn("cancelled 0", output)

    def test_hours_option_overrides_the_default(self):
        user = make_user()
        old_enough = backdate(make_unpaid_order(user), 5)
        too_young = backdate(make_unpaid_order(user), 3)

        self.run_command(hours=4)

        old_enough.refresh_from_db()
        too_young.refresh_from_db()
        self.assertEqual(old_enough.status, Order.Status.CANCELLED)
        self.assertEqual(too_young.status, Order.Status.PENDING)

    def test_default_threshold_comes_from_settings(self):
        user = make_user()
        order = backdate(make_unpaid_order(user), 3)
        with override_settings(ORDER_EXPIRY_HOURS=2):
            self.run_command()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_old_paid_order_is_never_cancelled_and_stock_stays_decremented(self):
        user = make_user()
        product = make_product(stock_quantity=10)
        order = make_unpaid_order(user, product=product)
        pay_order(user, order)
        backdate(order, 72)
        product.refresh_from_db()
        stock_after_payment = product.stock_quantity
        self.assertEqual(stock_after_payment, 9)

        output = self.run_command()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertIn("cancelled 0", output)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, stock_after_payment)

    def test_old_order_with_failed_payment_attempt_is_cancelled(self):
        user = make_user()
        order = make_unpaid_order(user)
        payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]
        handle_callback({
            "authority": payment.gateway_transaction_id,
            "status": "failed",
            "sig": _sign(payment.gateway_transaction_id, "failed"),
        })
        backdate(order, 48)

        self.run_command()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)

    def test_expiry_moves_no_stock_for_unpaid_orders(self):
        user = make_user()
        product = make_product(stock_quantity=10)
        order = make_unpaid_order(user, product=product, quantity=3)
        backdate(order, 48)

        self.run_command()

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 10, "stock moved for an order that never paid")
        order.refresh_from_db()
        self.assertEqual(order.refund_status, Order.RefundStatus.NONE)  # no money, no refund
        self.assertIsNone(order.stock_restored_at)

    def test_terminal_and_advanced_orders_are_untouched(self):
        user = make_user()
        cancelled = make_unpaid_order(user)
        cancelled.status = Order.Status.CANCELLED
        cancelled.save(update_fields=["status"])
        backdate(cancelled, 48)

        output = self.run_command()

        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, Order.Status.CANCELLED)
        self.assertIn("cancelled 0", output)

    def test_repeated_runs_are_idempotent(self):
        user = make_user()
        order = backdate(make_unpaid_order(user), 48)

        first = self.run_command()
        second = self.run_command()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIn("cancelled 1", first)
        self.assertIn("cancelled 0", second)

    def test_dry_run_lists_but_changes_nothing(self):
        user = make_user()
        order = backdate(make_unpaid_order(user), 48)

        output = self.run_command(dry_run=True)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertIn(f"WOULD CANCEL {order.order_number}", output)
        self.assertIn("nothing was changed", output)

    def test_order_paid_between_selection_and_cancel_is_skipped(self):
        """The mid-run race, tested at the guard itself: an order that
        stopped being unpaid/expirable after the queryset read must be
        left completely alone by the locked re-check."""
        user = make_user()
        order = backdate(make_unpaid_order(user), 48)
        pay_order(user, order)  # paid AFTER "selection", before the lock
        cutoff = timezone.now() - timedelta(hours=24)

        result = Command._cancel_if_still_unpaid(order.pk, cutoff)

        self.assertFalse(result)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_customer_who_pays_after_expiry_has_money_recorded_and_flagged(self):
        """End-to-end for the one unavoidable race: the order expires,
        THEN the gateway callback verifies a real capture. The command
        must not have broken the money path -- the payment is recorded
        and the order is flagged refund-required."""
        user = make_user()
        product = make_product(stock_quantity=10)
        order = make_unpaid_order(user, product=product)
        payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]
        backdate(order, 48)

        self.run_command()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

        late = handle_callback({
            "authority": payment.gateway_transaction_id,
            "status": "ok",
            "sig": _sign(payment.gateway_transaction_id, "ok"),
        })

        late.refresh_from_db()
        self.assertEqual(late.status, Payment.Status.SUCCESS)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.refund_status, Order.RefundStatus.REQUIRED)
        self.assertEqual(order.refund_amount, payment.amount)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 10)  # never fulfilled
