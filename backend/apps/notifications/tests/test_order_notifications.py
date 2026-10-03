"""
Order-event notification tests (Phase D).

Everything runs through the REAL flows: payments go through the real
initiate/callback path (mock gateway, real signatures), shipping goes
through workflow.set_status -- the notification layer is exercised
exactly where production triggers it. Delivery is deferred with
transaction.on_commit, so tests execute the deferred callbacks with
captureOnCommitCallbacks(execute=True), which also proves the deferral
itself (a rolled-back transaction must send nothing).

The SMS provider is the recording fake (tests/helpers.py); email is
Django's locmem backend (mail.outbox) -- no network anywhere.
"""
from django.core import mail
from django.db import transaction
from django.test import override_settings

from apps.core.testing import CacheIsolatedAPITestCase
from apps.notifications.services import Events, notify_order_event
from apps.orders.models import Order
from apps.orders.workflow import set_status
from apps.payments.gateways.mock import _sign
from apps.payments.services import handle_callback, initiate_payment
from apps.payments.tests.helpers import make_product, make_unpaid_order, make_user

from ..models import NotificationLog
from .helpers import install_fake_provider, provider_error

CALLBACK = "http://testserver/api/v1/payments/callback/"


def signed_ok(authority):
    return {"authority": authority, "status": "ok", "sig": _sign(authority, "ok")}


class OrderNotificationTestBase(CacheIsolatedAPITestCase):
    def pay_order(self, user, order):
        """Pay through the real flow and RUN the deferred notifications."""
        payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]
        with self.captureOnCommitCallbacks(execute=True):
            handle_callback(signed_ok(payment.gateway_transaction_id))
        order.refresh_from_db()
        return payment

    def ship_order(self, order):
        set_status(order, Order.Status.PROCESSING)
        order.refresh_from_db()
        order.tracking_code = "POST-778899"
        order.save(update_fields=["tracking_code"])
        with self.captureOnCommitCallbacks(execute=True):
            set_status(order, Order.Status.SHIPPED)
        order.refresh_from_db()
        return order


class OrderConfirmedNotificationTests(OrderNotificationTestBase):
    def test_payment_success_notifies_sms_and_email_with_masked_logs(self):
        fake = install_fake_provider(self)
        user = make_user(phone="+989121112233", email="buyer@example.com")
        order = make_unpaid_order(user)

        self.pay_order(user, order)

        # SMS actually "sent" to the ACCOUNT phone with a Persian message
        # carrying the order number...
        self.assertEqual(len(fake.sent), 1)
        self.assertEqual(fake.sent[0]["recipient"], "+989121112233")
        self.assertIn(order.order_number, fake.sent[0]["message"])
        # The amount appears in the usual grouped form (150,000 تومان).
        self.assertIn(f"{order.total:,}", fake.sent[0]["message"])

        # ...and an email with the confirmation subject.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("buyer@example.com", mail.outbox[0].to)
        self.assertIn(order.order_number, mail.outbox[0].subject)

        # Audit rows: one per channel, SENT, provider id recorded, and
        # recipients MASKED (raw contact data must not be in the log).
        sms_log = NotificationLog.objects.get(event=Events.ORDER_CONFIRMED, channel="sms")
        email_log = NotificationLog.objects.get(event=Events.ORDER_CONFIRMED, channel="email")
        self.assertEqual(sms_log.status, NotificationLog.Status.SENT)
        self.assertEqual(sms_log.provider_message_id, "FAKE-MSG-1")
        self.assertEqual(email_log.status, NotificationLog.Status.SENT)
        self.assertNotIn("+989121112233", sms_log.recipient_masked)
        self.assertIn("*", sms_log.recipient_masked)
        self.assertTrue(sms_log.recipient_masked.endswith("233"))
        self.assertNotIn("buyer@example.com", email_log.recipient_masked)
        self.assertIn("b***@example.com", email_log.recipient_masked)
        self.assertEqual(sms_log.order_id, order.pk)

    def test_sms_only_customer_gets_no_email_row(self):
        fake = install_fake_provider(self)
        user = make_user(phone="+989121112234")  # no email
        order = make_unpaid_order(user)

        self.pay_order(user, order)

        self.assertEqual(len(fake.sent), 1)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(
            NotificationLog.objects.filter(event=Events.ORDER_CONFIRMED, channel="email").count(), 0,
            "an account without an email is not an incident -- no email log row",
        )

    def test_provider_failure_never_breaks_the_payment(self):
        install_fake_provider(self, error=provider_error("kavenegar unreachable"))
        user = make_user(phone="+989121112235", email="buyer2@example.com")
        order = make_unpaid_order(user)
        product = order.items.first().product

        self.pay_order(user, order)  # must NOT raise

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 9)  # real payment effect intact

        sms_log = NotificationLog.objects.get(event=Events.ORDER_CONFIRMED, channel="sms")
        self.assertEqual(sms_log.status, NotificationLog.Status.FAILED)
        self.assertIn("kavenegar unreachable", sms_log.error)
        # The email channel is independent: it still went out.
        self.assertEqual(len(mail.outbox), 1)

    def test_unexpected_provider_exception_is_contained(self):
        """Even a non-SMSProviderError (a bug in a future provider) must
        degrade to a FAILED log row, never to a broken payment."""
        install_fake_provider(self, error=RuntimeError("unexpected provider bug"))
        user = make_user(phone="+989121112236")
        order = make_unpaid_order(user)

        self.pay_order(user, order)

        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        log = NotificationLog.objects.get(event=Events.ORDER_CONFIRMED, channel="sms")
        self.assertEqual(log.status, NotificationLog.Status.FAILED)
        self.assertIn("RuntimeError", log.error)

    def test_smtp_failure_never_breaks_the_payment(self):
        from unittest import mock

        install_fake_provider(self)
        with mock.patch(
            "apps.notifications.services.send_mail",
            side_effect=OSError("smtp connection refused"),
        ):
            user = make_user(phone="+989121112237", email="buyer3@example.com")
            order = make_unpaid_order(user)
            self.pay_order(user, order)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        email_log = NotificationLog.objects.get(event=Events.ORDER_CONFIRMED, channel="email")
        self.assertEqual(email_log.status, NotificationLog.Status.FAILED)
        self.assertIn("smtp connection refused", email_log.error)

    def test_replayed_callback_does_not_notify_twice(self):
        """Idempotency, end to end: the payment callback is replayed
        (terminal fast-path) and a second delivery of the same event is
        attempted directly -- the NotificationLog unique constraint keeps
        exactly one send per (event, order, channel)."""
        fake = install_fake_provider(self)
        user = make_user(phone="+989121112238", email="buyer4@example.com")
        order = make_unpaid_order(user)
        payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]

        with self.captureOnCommitCallbacks(execute=True):
            handle_callback(signed_ok(payment.gateway_transaction_id))
            # Full replay of the same callback:
            handle_callback(signed_ok(payment.gateway_transaction_id))
            # And a buggy/duplicated direct trigger for good measure:
            order.refresh_from_db()
            notify_order_event(order, Events.ORDER_CONFIRMED)

        self.assertEqual(len(fake.sent), 1, "SMS sent more than once for one event")
        self.assertEqual(len(mail.outbox), 1, "email sent more than once for one event")
        self.assertEqual(NotificationLog.objects.filter(event=Events.ORDER_CONFIRMED).count(), 2)

    def test_rolled_back_transaction_sends_nothing(self):
        """on_commit is the reliability rule: a transaction that never
        commits (payment verification rolled back) must not notify."""
        fake = install_fake_provider(self)
        user = make_user(phone="+989121112239", email="buyer5@example.com")
        order = make_unpaid_order(user)

        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    notify_order_event(order, Events.ORDER_CONFIRMED)
                    raise RuntimeError("payment verification blew up -- rolling back")
            except RuntimeError:
                pass

        self.assertEqual(fake.sent, [])
        self.assertEqual(mail.outbox, [])
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_sms_disabled_skips_sms_channel_entirely(self):
        fake = install_fake_provider(self)
        user = make_user(phone="+989121112240", email="buyer6@example.com")
        order = make_unpaid_order(user)

        with override_settings(SMS_ENABLED=False):
            self.pay_order(user, order)

        self.assertEqual(fake.sent, [])
        self.assertEqual(
            NotificationLog.objects.filter(channel="sms").count(), 0,
            "an explicit SMS_ENABLED=False opt-out is not an incident -- no log noise",
        )
        self.assertEqual(len(mail.outbox), 1)  # email channel unaffected

    def test_email_skipped_with_clear_reason_when_smtp_unconfigured(self):
        install_fake_provider(self)
        user = make_user(phone="+989121112241", email="buyer7@example.com")
        order = make_unpaid_order(user)

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST="",
        ):
            self.pay_order(user, order)

        email_log = NotificationLog.objects.get(event=Events.ORDER_CONFIRMED, channel="email")
        self.assertEqual(email_log.status, NotificationLog.Status.SKIPPED)
        self.assertIn("EMAIL_HOST", email_log.error)


class OrderShippedNotificationTests(OrderNotificationTestBase):
    def test_shipping_notifies_with_the_tracking_code(self):
        fake = install_fake_provider(self)
        user = make_user(phone="+989121112242", email="buyer8@example.com")
        order = make_unpaid_order(user)
        self.pay_order(user, order)
        mail.outbox.clear()
        fake.sent.clear()

        self.ship_order(order)

        self.assertEqual(len(fake.sent), 1)
        self.assertIn("POST-778899", fake.sent[0]["message"])
        self.assertIn(order.order_number, fake.sent[0]["message"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("POST-778899", mail.outbox[0].body)
        self.assertIn("ارسال شد", mail.outbox[0].subject)

        logs = NotificationLog.objects.filter(event=Events.ORDER_SHIPPED)
        self.assertEqual(logs.count(), 2)  # sms + email
        self.assertTrue(all(log.status == NotificationLog.Status.SENT for log in logs))

    def test_repeat_shipped_save_does_not_notify_again(self):
        fake = install_fake_provider(self)
        user = make_user(phone="+989121112243")
        order = make_unpaid_order(user)
        self.pay_order(user, order)
        self.ship_order(order)
        fake.sent.clear()

        # set_status(SHIPPED) again -> the workflow's no-op short-circuit
        # must prevent a second notification entirely.
        with self.captureOnCommitCallbacks(execute=True):
            set_status(order, Order.Status.SHIPPED)

        self.assertEqual(fake.sent, [])
        self.assertEqual(NotificationLog.objects.filter(event=Events.ORDER_SHIPPED).count(), 1)

    def test_shipped_sms_failure_does_not_break_the_status_change(self):
        install_fake_provider(self, error=provider_error("no credit"))
        user = make_user(phone="+989121112244")
        order = make_unpaid_order(user)
        self.pay_order(user, order)

        self.ship_order(order)  # must NOT raise

        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertEqual(order.tracking_code, "POST-778899")
        log = NotificationLog.objects.get(event=Events.ORDER_SHIPPED, channel="sms")
        self.assertEqual(log.status, NotificationLog.Status.FAILED)
        self.assertIn("no credit", log.error)


class NotificationLogAdminTests(OrderNotificationTestBase):
    def test_admin_is_strictly_read_only(self):
        from django.contrib.admin.sites import AdminSite

        from apps.notifications.admin import NotificationLogAdmin

        admin_instance = NotificationLogAdmin(NotificationLog, AdminSite())
        self.assertFalse(admin_instance.has_add_permission(None))
        self.assertFalse(admin_instance.has_change_permission(None))
        self.assertFalse(admin_instance.has_delete_permission(None))

    def test_log_survives_order_deletion_path_as_set_null(self):
        """SET_NULL audit retention: the FK must not cascade."""
        field = NotificationLog._meta.get_field("order")
        from django.db.models.deletion import SET_NULL

        self.assertIs(field.remote_field.on_delete, SET_NULL)
