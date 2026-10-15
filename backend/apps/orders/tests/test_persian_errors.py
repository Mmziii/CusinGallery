"""
Every owner-facing error from the order workflow and the refund ledger
must be in Persian.

The owner reads these messages in the admin; four of them were still raw
English («Cannot change an order from…», «Enter the carrier tracking
code…», «This order has no flagged refund…», «Enter the refund note…»),
which is unreadable to the person who has to act on them.

These tests are deliberately ASCII-based: they fail if any of the
messages leaks back into English, and they double as a "the message is
not empty / not a repr" guard.
"""
import re

from django.test import TestCase, override_settings

from apps.orders.models import Order
from apps.orders.refunds import RefundError, mark_refunded, validate_admin_refund_change
from apps.orders.workflow import (
    OrderWorkflowError,
    check_transition,
    set_status,
)
from apps.payments.tests.helpers import make_product, make_unpaid_order, make_user

S = Order.Status
PS = Order.PaymentStatus

# Words that must NEVER reach the owner. Small list on purpose: it is the
# vocabulary of the four messages that were reported, plus the two the
# refund module shares with them.
FORBIDDEN = (
    "Cannot change an order",
    "Allowed next statuses",
    "terminal status",
    "Enter the carrier tracking code",
    "This order has no flagged refund",
    "Enter the refund note",
    "A completed refund cannot",
    "Refund state cannot be cleared",
)

ASCII_WORD = re.compile(r"[A-Za-z]{4,}")

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


def assert_persian(testcase, message, what):
    text = str(message)
    testcase.assertTrue(text.strip(), f"{what}: empty message")
    for english in FORBIDDEN:
        testcase.assertNotIn(english, text, f"{what}: still English")
    # Persian must actually dominate: a stray Latin word or two (SKU, PSP)
    # is fine, a whole English sentence is not.
    letters = re.findall(r"[\u0600-\u06FF]", text)
    testcase.assertGreater(
        len(letters), len(ASCII_WORD.findall(text)) * 2,
        f"{what}: message is not predominantly Persian -> {text!r}",
    )


@override_settings(**PLAIN_STATIC)
class WorkflowErrorLanguageTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(stock_quantity=10)
        self.order = make_unpaid_order(self.user, product=self.product, quantity=1)

    def test_illegal_dag_transition_is_persian(self):
        with self.assertRaises(OrderWorkflowError) as caught:
            check_transition(S.PENDING, S.DELIVERED, tracking_code="X")
        message = str(caught.exception)
        assert_persian(self, message, "pending -> delivered")
        self.assertIn("در انتظار تأیید", message)
        self.assertIn("تحویل شده", message)

    def test_terminal_status_message_names_the_status(self):
        with self.assertRaises(OrderWorkflowError) as caught:
            check_transition(S.CANCELLED, S.CONFIRMED, tracking_code="X")
        message = str(caught.exception)
        assert_persian(self, message, "cancelled -> confirmed")
        self.assertIn("پایانی", message)

    def test_missing_tracking_code_is_persian(self):
        with self.assertRaises(OrderWorkflowError) as caught:
            check_transition(
                S.PROCESSING, S.SHIPPED, tracking_code="",
                payment_status=PS.PAID,
            )
        message = str(caught.exception)
        assert_persian(self, message, "shipped without tracking code")
        self.assertIn("کد رهگیری", message)
        self.assertIn("ارسال شده", message)

    def test_unpaid_confirmation_block_is_persian(self):
        with self.assertRaises(OrderWorkflowError) as caught:
            set_status(self.order, S.CONFIRMED)
        assert_persian(self, caught.exception, "unpaid -> confirmed")


@override_settings(**PLAIN_STATIC)
class RefundErrorLanguageTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(stock_quantity=10)
        self.order = make_unpaid_order(self.user, product=self.product, quantity=1)

    def test_nothing_flagged_message_is_persian(self):
        with self.assertRaises(RefundError) as caught:
            mark_refunded(self.order, note="مرجع: ۱۲۳")
        message = str(caught.exception)
        assert_persian(self, message, "refund with nothing flagged")
        self.assertIn("بازپرداخت", message)

    def test_missing_note_message_is_persian(self):
        self.order.refund_status = Order.RefundStatus.REQUIRED
        self.order.refund_amount = self.order.total
        self.order.save(update_fields=["refund_status", "refund_amount"])
        with self.assertRaises(RefundError) as caught:
            mark_refunded(self.order, note="   ")
        message = str(caught.exception)
        assert_persian(self, message, "refund without a note")
        self.assertIn("یادداشت", message)

    def test_regression_from_refunded_message_is_persian(self):
        self.order.refund_status = Order.RefundStatus.REFUNDED
        self.order.save(update_fields=["refund_status"])
        with self.assertRaises(RefundError) as caught:
            validate_admin_refund_change(self.order, Order.RefundStatus.REQUIRED)
        assert_persian(self, caught.exception, "refunded -> required")

    def test_clearing_the_ledger_message_is_persian(self):
        self.order.refund_status = Order.RefundStatus.REQUIRED
        self.order.save(update_fields=["refund_status"])
        with self.assertRaises(RefundError) as caught:
            validate_admin_refund_change(self.order, Order.RefundStatus.NONE)
        assert_persian(self, caught.exception, "required -> none")

    def test_an_empty_note_never_saves_a_refund(self):
        """The rule, not just the wording."""
        self.order.refund_status = Order.RefundStatus.REQUIRED
        self.order.refund_amount = self.order.total
        self.order.save(update_fields=["refund_status", "refund_amount"])
        with self.assertRaises(RefundError):
            mark_refunded(self.order, note="")
        self.order.refresh_from_db()
        self.assertEqual(self.order.refund_status, Order.RefundStatus.REQUIRED)
        self.assertIsNone(self.order.refunded_at)
