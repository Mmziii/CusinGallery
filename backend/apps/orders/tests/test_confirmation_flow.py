"""
Owner confirmation is a separate step from payment.

Payment used to flip an order straight to «تأیید شده», which told the
customer the shop had accepted an order nobody had looked at. Now a paid
order stays «در انتظار تأیید» until the OWNER confirms it:

    paid + pending  --owner-->  confirmed -> processing -> shipped -> delivered

and an unpaid order can NEVER reach confirmed (or anything after it) --
only «لغو شده» stays open to it.

Covered here: the workflow gate, the admin page (warning + hidden buttons),
the quick-status endpoint, and the «پرداخت‌شده‌های در انتظار تأیید» queue.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.notifications.services import Events
from apps.notifications.models import NotificationLog
from apps.orders.admin import ORDER_QUEUES, QUEUE_FILTERS
from apps.orders.models import Order
from apps.orders.workflow import (
    OrderWorkflowError,
    allowed_next_statuses,
    payment_block_reason,
    requires_payment,
    set_status,
)
from apps.payments.gateways.mock import _sign
from apps.payments.services import handle_callback, initiate_payment
from apps.payments.tests.helpers import make_product, make_unpaid_order, make_user

from apps.adminui.tests.helpers import PLAIN_STATIC, make_order, make_superuser

CALLBACK = "http://testserver/api/v1/payments/callback/"
S = Order.Status


def signed_ok(authority):
    return {"authority": authority, "status": "ok", "sig": _sign(authority, "ok")}


@override_settings(**PLAIN_STATIC)
class PaymentGateTests(TestCase):
    """The workflow rule itself."""

    def setUp(self):
        self.user = make_user()
        self.product = make_product(stock_quantity=10)
        self.order = make_unpaid_order(self.user, product=self.product, quantity=1)

    def pay(self):
        payment = initiate_payment(self.user, self.order.pk, callback_url=CALLBACK)["payment"]
        handle_callback(signed_ok(payment.gateway_transaction_id))
        self.order.refresh_from_db()
        return payment

    def test_payment_does_not_confirm_the_order(self):
        self.pay()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, S.PENDING)
        self.assertEqual(self.order.get_status_display(), "در انتظار تأیید")

    def test_unpaid_order_cannot_be_confirmed(self):
        with self.assertRaises(OrderWorkflowError) as caught:
            set_status(self.order, S.CONFIRMED)
        self.assertIn("پرداخت نشده", str(caught.exception))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, S.PENDING)

    def test_no_fulfilment_status_is_reachable_on_an_unpaid_order(self):
        """Bypass the DAG (set the row directly) and the payment gate
        still refuses every fulfilment status -- it is NOT only the
        pending->confirmed edge that is protected."""
        for target in (S.PROCESSING, S.SHIPPED, S.DELIVERED):
            for current in (S.CONFIRMED, S.PROCESSING, S.SHIPPED):
                if target not in allowed_next_statuses(current):
                    continue
                with self.subTest(current=current, target=target):
                    order = make_unpaid_order(self.user, product=self.product, quantity=1)
                    Order.objects.filter(pk=order.pk).update(status=current)
                    order.refresh_from_db()
                    with self.assertRaises(OrderWorkflowError) as caught:
                        set_status(order, target)
                    self.assertIn("پرداخت نشده", str(caught.exception))

    def test_unpaid_order_can_still_be_cancelled(self):
        set_status(self.order, S.CANCELLED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, S.CANCELLED)

    def test_paid_order_confirms_and_then_walks_the_whole_flow(self):
        self.pay()
        for target in (S.CONFIRMED, S.PROCESSING, S.SHIPPED, S.DELIVERED):
            if target == S.SHIPPED:
                self.order.tracking_code = "POST-1"
                self.order.save(update_fields=["tracking_code"])
            set_status(self.order, target)
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, target)

    def test_requires_payment_covers_every_fulfilment_status(self):
        for status in (S.CONFIRMED, S.PROCESSING, S.SHIPPED, S.DELIVERED):
            self.assertTrue(requires_payment(status), status)
        for status in (S.PENDING, S.CANCELLED, S.RETURNED):
            self.assertFalse(requires_payment(status), status)

    def test_payment_block_reason_message(self):
        # Cancel is never blocked by payment.
        self.assertEqual(payment_block_reason(self.order, S.CANCELLED), "")
        # Fulfilment is blocked while unpaid ...
        reason = payment_block_reason(self.order, S.CONFIRMED)
        self.assertIn("پرداخت نشده", reason)
        self.assertIn("تأیید شده", reason)
        self.assertIn("لغو شده", reason)
        # ... and clear once paid.
        self.pay()
        self.assertEqual(payment_block_reason(self.order, S.CONFIRMED), "")

    def test_a_failed_payment_does_not_open_the_gate(self):
        payment = initiate_payment(self.user, self.order.pk, callback_url=CALLBACK)["payment"]
        handle_callback({
            "authority": payment.gateway_transaction_id,
            "status": "failed",
            "sig": _sign(payment.gateway_transaction_id, "failed"),
        })
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)
        with self.assertRaises(OrderWorkflowError):
            set_status(self.order, S.CONFIRMED)

    def test_the_dag_itself_is_unchanged(self):
        """Only the payment rule is new -- the edges are the same."""
        self.assertEqual(allowed_next_statuses(S.PENDING), {S.CONFIRMED, S.CANCELLED})

    def test_owner_confirmation_notifies_the_customer(self):
        self.pay()
        self.assertEqual(
            NotificationLog.objects.filter(event=Events.ORDER_CONFIRMED).count(), 0,
            "the payment must not claim the shop confirmed the order",
        )
        with self.captureOnCommitCallbacks(execute=True):
            set_status(self.order, S.CONFIRMED)
        self.assertEqual(
            NotificationLog.objects.filter(event=Events.ORDER_CONFIRMED).count(), 1,
        )


@override_settings(**PLAIN_STATIC)
class ConfirmationAdminTests(TestCase):
    """What the owner SEES: the warning and the dead buttons."""

    def setUp(self):
        self.admin = make_superuser(username="confirmowner", phone="+989000033001")
        self.client.force_login(self.admin)
        self.unpaid = make_order(status=S.PENDING, payment_status=Order.PaymentStatus.UNPAID)
        self.paid_pending = make_order(status=S.PENDING, payment_status=Order.PaymentStatus.PAID)

    def _page(self, order):
        return self.client.get(reverse("admin:orders_order_change", args=[order.pk]))

    def test_unpaid_order_shows_the_unpaid_warning(self):
        html = self._page(self.unpaid).content.decode()
        self.assertIn("cusin-quick-warning", html)
        self.assertIn("پرداخت نشده", html)

    def test_a_cancelled_unpaid_order_does_not_warn_about_cancelling(self):
        """The red «فقط می‌توان آن را لغو کرد» banner stayed on terminal
        orders, describing an action the page no longer offers."""
        cancelled = make_order(
            status=S.CANCELLED, payment_status=Order.PaymentStatus.UNPAID
        )
        html = self._page(cancelled).content.decode()
        self.assertNotIn("cusin-quick-warning", html)
        self.assertNotIn("فقط می‌توان آن را لغو کرد", html)

    def test_a_returned_unpaid_order_does_not_warn_either(self):
        returned = make_order(
            status=S.RETURNED, payment_status=Order.PaymentStatus.UNPAID
        )
        html = self._page(returned).content.decode()
        self.assertNotIn("فقط می‌توان آن را لغو کرد", html)

    def test_the_warning_covers_every_pending_unpaid_order(self):
        """Pending is the one status where the sentence is true."""
        for status in (S.PENDING,):
            order = make_order(status=status, payment_status=Order.PaymentStatus.UNPAID)
            context = self._page(order).context
            with self.subTest(status=status):
                self.assertTrue(context["unpaid_warning"])

    def test_no_other_status_warns_about_payment(self):
        """Context-level, so every status is covered, not just two."""
        for status in (S.CONFIRMED, S.PROCESSING, S.SHIPPED, S.DELIVERED,
                       S.CANCELLED, S.RETURNED):
            order = make_order(status=status, payment_status=Order.PaymentStatus.UNPAID)
            context = self._page(order).context
            with self.subTest(status=status):
                self.assertEqual(context["unpaid_warning"], "")

    def test_unpaid_order_offers_only_cancel(self):
        context = self._page(self.unpaid).context
        allowed = [action["value"] for action in context["quick_allowed"]]
        self.assertEqual(allowed, [S.CANCELLED])
        blocked = {action["value"]: action["reason"] for action in context["quick_blocked"]}
        self.assertIn(S.CONFIRMED, blocked)
        self.assertIn("پرداخت نشده", blocked[S.CONFIRMED])

    def test_paid_pending_order_offers_confirmation_and_shows_the_hint(self):
        response = self._page(self.paid_pending)
        context = response.context
        allowed = [action["value"] for action in context["quick_allowed"]]
        self.assertEqual(allowed, [S.CONFIRMED, S.CANCELLED])
        self.assertEqual(context["quick_blocked"], [])
        self.assertTrue(context["awaiting_confirmation"])
        html = response.content.decode()
        self.assertIn("در انتظار", html)
        self.assertIn("تأیید شما", html)
        self.assertNotIn("cusin-quick-warning\" role=\"alert\"", html)

    def test_quick_status_refuses_to_confirm_an_unpaid_order(self):
        response = self.client.post(
            reverse("admin:orders_order_quick_status", args=[self.unpaid.pk]),
            {"next_status": S.CONFIRMED},
            follow=True,
        )
        self.unpaid.refresh_from_db()
        self.assertEqual(self.unpaid.status, S.PENDING)
        self.assertIn("پرداخت نشده", response.content.decode())

    def test_quick_status_can_cancel_an_unpaid_order(self):
        self.client.post(
            reverse("admin:orders_order_quick_status", args=[self.unpaid.pk]),
            {"next_status": S.CANCELLED},
        )
        self.unpaid.refresh_from_db()
        self.assertEqual(self.unpaid.status, S.CANCELLED)

    def test_quick_status_confirms_a_paid_order(self):
        self.client.post(
            reverse("admin:orders_order_quick_status", args=[self.paid_pending.pk]),
            {"next_status": S.CONFIRMED},
        )
        self.paid_pending.refresh_from_db()
        self.assertEqual(self.paid_pending.status, S.CONFIRMED)

    def test_saving_confirmed_on_an_unpaid_order_persists_nothing(self):
        """The change FORM (not just the quick buttons) is gated too."""
        response = self.client.post(
            reverse("admin:orders_order_change", args=[self.unpaid.pk]),
            {"status": S.CONFIRMED, "tracking_code": "", "refund_status": "none"},
        )
        self.unpaid.refresh_from_db()
        self.assertEqual(self.unpaid.status, S.PENDING)
        if response.status_code == 200:
            self.assertIn("پرداخت نشده", response.content.decode())


@override_settings(**PLAIN_STATIC)
class ConfirmationQueueTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="queueowner", phone="+989000034001")
        self.client.force_login(self.admin)
        self.awaiting = make_order(status=S.PENDING, payment_status=Order.PaymentStatus.PAID)
        self.processing = make_order(status=S.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        self.unpaid = make_order(status=S.PENDING, payment_status=Order.PaymentStatus.UNPAID)

    def test_the_awaiting_confirmation_queue_exists_and_is_labelled(self):
        labels = {key: label for key, label, _icon in ORDER_QUEUES}
        self.assertEqual(labels["awaiting_confirmation"], "پرداخت‌شده‌های در انتظار تأیید")
        self.assertEqual(labels["paid_to_process"], "تأیید‌شدهٔ در حال آماده‌سازی")

    def test_the_queues_split_paid_orders_correctly(self):
        awaiting = Order.objects.filter(QUEUE_FILTERS["awaiting_confirmation"])
        processing = Order.objects.filter(QUEUE_FILTERS["paid_to_process"])
        self.assertEqual(list(awaiting), [self.awaiting])
        self.assertEqual(list(processing), [self.processing])

    def test_the_tab_counts_and_the_linked_changelist_agree(self):
        response = self.client.get(reverse("admin:orders_order_changelist"))
        tabs = {tab["key"]: tab for tab in response.context["queue_tabs"]}
        self.assertEqual(tabs["awaiting_confirmation"]["count"], 1)
        self.assertEqual(tabs["paid_to_process"]["count"], 1)

        listing = self.client.get(
            reverse("admin:orders_order_changelist") + "?queue=awaiting_confirmation"
        )
        self.assertEqual(
            [row.pk for row in listing.context["cl"].queryset], [self.awaiting.pk]
        )
