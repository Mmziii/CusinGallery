"""
Owner alert tests (Part R4 item 3).

Real flows only: payments run through the genuine initiate/callback path
(mock gateway, real signatures) exactly like test_order_notifications.py,
and low-stock alerts run through the genuine inventory decrement. The SMS
provider is the recording fake; email is Django's locmem outbox; the
Telegram/Bale adapters are exercised against a mocked requests.post
(their live APIs are never called from tests).
"""
from unittest import mock

from django.core import mail
from django.test import override_settings

from apps.core.testing import CacheIsolatedAPITestCase
from apps.notifications.messengers import (
    BaleMessenger,
    MessengerError,
    TelegramMessenger,
    get_enabled_messengers,
)
from apps.notifications.models import NotificationLog
from apps.payments.tests.helpers import make_product, make_unpaid_order, make_user

from .helpers import install_fake_provider, provider_error

OWNER_PHONE = "+989000000001"
OWNER_EMAIL = "owner@cusin.example"
CUSTOMER_PHONE = "+989121112233"

ALERT_SETTINGS = dict(
    OWNER_ALERT_PHONES=OWNER_PHONE,
    OWNER_ALERT_EMAILS=OWNER_EMAIL,
)

from apps.notifications.tests.test_order_notifications import (  # noqa: E402
    OrderNotificationTestBase,
)


class OwnerPaidOrderAlertTests(OrderNotificationTestBase):
    @override_settings(**ALERT_SETTINGS)
    def test_paid_order_alerts_owner_by_sms_and_email(self):
        fake = install_fake_provider(self)
        user = make_user(phone=CUSTOMER_PHONE, email="buyer@example.com",
                         first_name="سارا", last_name="احمدی")
        product = make_product(price=150000)
        order = make_unpaid_order(user, product, quantity=2)

        self.pay_order(user, order)

        owner_sends = [s for s in fake.sent if s["recipient"] == OWNER_PHONE]
        self.assertEqual(len(owner_sends), 1)
        text = owner_sends[0]["message"]
        self.assertIn(order.order_number, text)
        self.assertIn(f"{order.total:,}", text)  # total in Toman (incl. shipping)
        self.assertIn("تعداد اقلام: 2", text)    # item count
        self.assertIn("روش ارسال", text)         # shipping method label
        self.assertIn("سارا احمدی", text)        # customer name
        self.assertIn(CUSTOMER_PHONE, text)      # customer phone
        self.assertIn(f"/orders/order/{order.pk}/change/", text)  # admin link

        self.assertEqual(len(mail.outbox), 2)    # customer + owner emails
        owner_mail = [m for m in mail.outbox if OWNER_EMAIL in m.to]
        self.assertEqual(len(owner_mail), 1)
        self.assertIn(order.order_number, owner_mail[0].subject)

        logs = NotificationLog.objects.filter(event="owner_paid_order")
        self.assertEqual(
            {(log.channel, log.status) for log in logs},
            {(NotificationLog.Channel.SMS, NotificationLog.Status.SENT),
             (NotificationLog.Channel.EMAIL, NotificationLog.Status.SENT)},
        )

    @override_settings(**ALERT_SETTINGS)
    def test_unpaid_order_sends_no_owner_alert(self):
        fake = install_fake_provider(self)
        user = make_user(phone=CUSTOMER_PHONE)
        order = make_unpaid_order(user, make_product())

        self.assertFalse(
            NotificationLog.objects.filter(event="owner_paid_order").exists()
        )
        self.assertEqual([s for s in fake.sent if s["recipient"] == OWNER_PHONE], [])

    @override_settings(**ALERT_SETTINGS)
    def test_replayed_callback_is_idempotent_for_the_owner_alert(self):
        fake = install_fake_provider(self)
        user = make_user(phone=CUSTOMER_PHONE)
        order = make_unpaid_order(user, make_product())

        from apps.payments.services import handle_callback, initiate_payment
        from apps.notifications.tests.test_order_notifications import signed_ok

        payment = initiate_payment(user, order.pk, callback_url="http://testserver/api/v1/payments/callback/")["payment"]
        with self.captureOnCommitCallbacks(execute=True):
            handle_callback(signed_ok(payment.gateway_transaction_id))
            handle_callback(signed_ok(payment.gateway_transaction_id))  # replay

        owner_sends = [s for s in fake.sent if s["recipient"] == OWNER_PHONE]
        self.assertEqual(len(owner_sends), 1)
        self.assertEqual(
            NotificationLog.objects.filter(event="owner_paid_order",
                                           channel=NotificationLog.Channel.SMS).count(),
            1,
        )

    def test_empty_recipient_list_sends_nothing(self):
        # Defaults: OWNER_ALERT_PHONES / OWNER_ALERT_EMAILS are empty.
        fake = install_fake_provider(self)
        user = make_user(phone=CUSTOMER_PHONE)
        order = make_unpaid_order(user, make_product())

        self.pay_order(user, order)

        self.assertEqual([s for s in fake.sent if s["recipient"] == OWNER_PHONE], [])
        self.assertFalse(
            NotificationLog.objects.filter(event="owner_paid_order").exists()
        )

    @override_settings(**ALERT_SETTINGS)
    def test_owner_sms_failure_never_breaks_the_payment(self):
        install_fake_provider(self, error=provider_error("owner sms down"))
        user = make_user(phone=CUSTOMER_PHONE)
        order = make_unpaid_order(user, make_product())

        self.pay_order(user, order)  # must not raise

        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")
        owner_log = NotificationLog.objects.get(
            event="owner_paid_order", channel=NotificationLog.Channel.SMS
        )
        self.assertEqual(owner_log.status, NotificationLog.Status.FAILED)
        self.assertIn("owner sms down", owner_log.error)


class OwnerLowStockAlertTests(OrderNotificationTestBase):
    def _pay(self, user, product, quantity):
        order = make_unpaid_order(user, product, quantity=quantity)
        self.pay_order(user, order)
        return order

    def low_stock_sends(self, fake):
        # The owner phone also receives the paid-order alert; keep only
        # the low-stock messages.
        return [s for s in fake.sent
                if s["recipient"] == OWNER_PHONE and "موجودی کم" in s["message"]]

    @override_settings(**ALERT_SETTINGS, LOW_STOCK_THRESHOLD=3)
    def test_crossing_down_alerts_once_and_rearms_after_restock(self):
        fake = install_fake_provider(self)
        user = make_user(phone=CUSTOMER_PHONE)
        product = make_product(name="کتری استیل", stock_quantity=5)

        # 5 -> 2 crosses threshold 3: exactly ONE alert.
        self._pay(user, product, quantity=3)
        owner_sends = self.low_stock_sends(fake)
        self.assertEqual(len(owner_sends), 1)
        self.assertIn("کتری استیل", owner_sends[0]["message"])
        self.assertIn("موجودی 2", owner_sends[0]["message"])

        # 2 -> 1 stays below: NO new alert.
        self._pay(user, product, quantity=1)
        owner_sends = self.low_stock_sends(fake)
        self.assertEqual(len(owner_sends), 1)

        # Restock above the threshold, then cross again: re-armed alert.
        product.stock_quantity = 6
        product.save()
        self._pay(user, product, quantity=4)  # 6 -> 2 crosses again
        owner_sends = self.low_stock_sends(fake)
        self.assertEqual(len(owner_sends), 2)
        # One SMS log row per crossing (email adds its own channel row).
        self.assertEqual(
            NotificationLog.objects.filter(
                event="owner_low_stock", channel=NotificationLog.Channel.SMS
            ).count(),
            2,
        )

    @override_settings(**ALERT_SETTINGS, LOW_STOCK_THRESHOLD=3)
    def test_no_alert_when_stock_stays_above_threshold(self):
        fake = install_fake_provider(self)
        user = make_user(phone=CUSTOMER_PHONE)
        product = make_product(stock_quantity=10)

        self._pay(user, product, quantity=2)  # 10 -> 8, still above 3

        self.assertEqual(self.low_stock_sends(fake), [])
        self.assertFalse(
            NotificationLog.objects.filter(event="owner_low_stock").exists()
        )


class MessengerAdapterTests(OrderNotificationTestBase):
    def test_disabled_by_default(self):
        self.assertEqual(get_enabled_messengers(), [])
        self.assertFalse(TelegramMessenger().enabled)
        self.assertFalse(BaleMessenger().enabled)

    @override_settings(TELEGRAM_BOT_TOKEN="tok-1", TELEGRAM_CHAT_ID="42",
                       BALE_BOT_TOKEN="tok-2", BALE_CHAT_ID="43")
    def test_enabled_when_token_and_chat_id_present(self):
        names = {m.name for m in get_enabled_messengers()}
        self.assertEqual(names, {"telegram", "bale"})

    @override_settings(TELEGRAM_BOT_TOKEN="tok-1", TELEGRAM_CHAT_ID="42",
                       TELEGRAM_API_BASE="https://api.telegram.org")
    def test_telegram_send_posts_telegram_shaped_payload(self):
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            response = mock.Mock()
            response.status_code = 200
            response.json.return_value = {"ok": True, "result": {"message_id": 7}}
            return response

        with mock.patch("apps.notifications.messengers.requests.post", side_effect=fake_post):
            message_id = TelegramMessenger().send("سلام")

        self.assertEqual(captured["url"], "https://api.telegram.org/bottok-1/sendMessage")
        self.assertEqual(captured["json"], {"chat_id": "42", "text": "سلام"})
        self.assertEqual(message_id, "7")

    @override_settings(BALE_BOT_TOKEN="tok-2", BALE_CHAT_ID="43")
    def test_bale_send_uses_documented_business_endpoint(self):
        # Verified against docs.bale.ai: POST
        # https://tapi.bale.ai/business/bot<TOKEN>/sendMessage
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            response = mock.Mock()
            response.status_code = 200
            response.json.return_value = {"ok": True, "result": {"message_id": 9}}
            return response

        with mock.patch("apps.notifications.messengers.requests.post", side_effect=fake_post):
            BaleMessenger().send("سلام")

        self.assertEqual(captured["url"],
                         "https://tapi.bale.ai/business/bottok-2/sendMessage")

    @override_settings(TELEGRAM_BOT_TOKEN="tok-1", TELEGRAM_CHAT_ID="42")
    def test_http_error_raises_messenger_error_without_token_leak(self):
        response = mock.Mock()
        response.status_code = 401

        with mock.patch("apps.notifications.messengers.requests.post", return_value=response):
            with self.assertRaises(MessengerError):
                TelegramMessenger().send("x")

    @override_settings(OWNER_ALERT_PHONES="", OWNER_ALERT_EMAILS="",
                       TELEGRAM_BOT_TOKEN="tok-1", TELEGRAM_CHAT_ID="42")
    def test_owner_alert_flows_through_messenger_channel(self):
        # Only the messenger channel is configured: SMS/email stay silent,
        # the messenger log row appears.
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["json"] = json
            response = mock.Mock()
            response.status_code = 200
            response.json.return_value = {"ok": True, "result": {"message_id": 3}}
            return response

        user = make_user(phone=CUSTOMER_PHONE)
        order = make_unpaid_order(user, make_product())
        with mock.patch("apps.notifications.messengers.requests.post", side_effect=fake_post):
            self.pay_order(user, order)

        self.assertIn(order.order_number, captured["json"]["text"])
        log = NotificationLog.objects.get(
            event="owner_paid_order", channel=NotificationLog.Channel.MESSENGER
        )
        self.assertEqual(log.status, NotificationLog.Status.SENT)
