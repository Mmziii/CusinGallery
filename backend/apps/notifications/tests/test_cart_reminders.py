"""
Part R5 item 11: opt-in cart-reminder SMS command.

Uses the FakeSMSProvider (records sends, can fail on demand) and a
faked clock -- no network, no provider credentials -- while the real
command code (eligibility rules, quiet hours, idempotency, cooldown,
audit logging) runs for real against a real database.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.core.testing import frozen_clock
from apps.notifications.models import NotificationLog
from apps.notifications.tests.helpers import install_fake_provider, provider_error
from apps.orders.models import Order
from apps.products.tests.helpers import make_product

TEHRAN = ZoneInfo("Asia/Tehran")

#: A "now" inside the allowed sending window (12:00 Tehran).
NOON = datetime(2026, 10, 5, 12, 0, tzinfo=TEHRAN)
#: A "now" inside quiet hours (22:00 Tehran).
NIGHT = datetime(2026, 10, 5, 22, 0, tzinfo=TEHRAN)

PATCH_TARGET = "apps.notifications.management.commands.send_cart_reminders"


@contextmanager
def at(moment):
    """Run the block at `moment`.

    The shared Django clock is faked, not just the command's own module
    binding: NotificationLog.created_at is auto_now_add, so a run that
    patched only the command would still stamp its audit rows with the
    real time and the NEXT run's cooldown check would compare that real
    timestamp against the fake "now" (see apps.core.testing.frozen_clock
    for the full post-mortem).
    """
    with frozen_clock(moment) as fake_now:
        yield fake_now


class CartReminderTestBase(TestCase):
    def setUp(self):
        super().setUp()
        from apps.accounts.tests.helpers import make_user

        self.user = make_user(marketing_sms_consent=True, phone="+989120000001")
        self.product = make_product(stock_quantity=10)
        self.cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        self.fake = install_fake_provider(
            self, also_patch=(f"{PATCH_TARGET}.get_provider",)
        )

    def age_cart(self, hours=30, now=None):
        """Make the whole cart state `hours` old relative to `now`."""
        t = (now or timezone.now()) - timedelta(hours=hours)
        Cart.objects.filter(pk=self.cart.pk).update(updated_at=t)
        self.cart.items.update(updated_at=t)
        self.cart.refresh_from_db()

    def change_cart_state(self, when):
        """Change the contents so the fingerprint changes, backdated to `when`."""
        CartItem.objects.filter(cart=self.cart).update(quantity=3, updated_at=when)
        Cart.objects.filter(pk=self.cart.pk).update(updated_at=when)

    def logs(self):
        return NotificationLog.objects.filter(event__startswith="cart_reminder_")

    def run_command(self):
        call_command("send_cart_reminders")


@override_settings(CART_REMINDER_ENABLED=True, SMS_ENABLED=True)
class CartReminderRuleTests(CartReminderTestBase):
    def test_sends_once_for_stale_consent_cart_with_opt_out_text(self):
        self.age_cart(now=NOON)
        with at(NOON):
            self.run_command()

        self.assertEqual(len(self.fake.sent), 1)
        message = self.fake.sent[0]["message"]
        self.assertIn("/cart/", message)
        # The opt-out instruction is part of the contract.
        self.assertIn("خاموش", message)
        log = self.logs().get()
        self.assertEqual(log.status, NotificationLog.Status.SENT)
        self.assertEqual(log.channel, NotificationLog.Channel.SMS)
        self.assertEqual(log.user_id, self.user.id)
        self.assertTrue(log.event.startswith("cart_reminder_"))

    def test_disabled_by_default_flag_sends_nothing(self):
        self.age_cart(now=NOON)
        with override_settings(CART_REMINDER_ENABLED=False), at(NOON):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 0)
        self.assertEqual(self.logs().count(), 0)

    def test_no_consent_no_send(self):
        self.user.marketing_sms_consent = False
        self.user.save(update_fields=["marketing_sms_consent"])
        self.age_cart(now=NOON)
        with at(NOON):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 0)

    def test_fresh_cart_is_not_reminded(self):
        self.age_cart(hours=1, now=NOON)  # changed an hour ago -- too fresh
        with at(NOON):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 0)

    def test_order_placed_after_cart_state_blocks_reminder(self):
        self.age_cart(now=NOON)
        order = Order.objects.create(
            user=self.user, subtotal=1000, total=1000,
            shipping_recipient_name="تست", shipping_phone="+989121234567",
            shipping_province="تهران", shipping_city="تهران",
            shipping_address="خیابان تست", shipping_postal_code="1234567890",
        )
        # The order was placed an hour after the cart state.
        Order.objects.filter(pk=order.pk).update(
            created_at=self.cart.updated_at + timedelta(hours=1)
        )
        with at(NOON):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 0)

    def test_same_cart_state_is_reminded_only_once(self):
        self.age_cart(now=NOON)
        with at(NOON):
            self.run_command()
            self.run_command()  # second hourly run, nothing changed
        self.assertEqual(len(self.fake.sent), 1)
        self.assertEqual(self.logs().count(), 1)

    def test_cooldown_blocks_a_new_state_within_seven_days(self):
        self.age_cart(now=NOON)
        with at(NOON):
            self.run_command()
        three_days_later = NOON + timedelta(days=3)
        self.change_cart_state(three_days_later - timedelta(hours=30))
        with at(three_days_later):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 1)  # still the first one only

    def test_new_state_after_cooldown_is_reminded_again(self):
        self.age_cart(now=NOON)
        with at(NOON):
            self.run_command()
        # The audit row carries the FAKED moment, not the real clock. This
        # assertion is the regression guard for the time bomb: with a real
        # created_at the cooldown comparison below silently measured
        # wall-clock time, so the test started failing the moment the real
        # date passed the fake "eight days later" (2026-10-06 12:00
        # Tehran).
        self.assertEqual(self.logs().get().created_at, NOON)

        eight_days_later = NOON + timedelta(days=8)
        self.change_cart_state(eight_days_later - timedelta(hours=30))
        with at(eight_days_later):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 2)
        self.assertEqual(self.logs().count(), 2)
        self.assertEqual(
            self.logs().order_by("created_at").last().created_at, eight_days_later
        )

    def test_quiet_hours_send_nothing_and_consume_nothing(self):
        self.age_cart(now=NIGHT)
        with at(NIGHT):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 0)
        self.assertEqual(self.logs().count(), 0)
        # Same cart, allowed window the next day: still deliverable.
        with at(NIGHT + timedelta(hours=14)):  # 12:00 next day
            self.run_command()
        self.assertEqual(len(self.fake.sent), 1)

    def test_empty_cart_is_never_reminded(self):
        self.cart.items.all().delete()
        Cart.objects.filter(pk=self.cart.pk).update(updated_at=NOON - timedelta(hours=40))
        with at(NOON):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 0)


class CartReminderFailureTests(CartReminderTestBase):
    @override_settings(CART_REMINDER_ENABLED=True, SMS_ENABLED=True)
    def test_provider_failure_is_logged_not_raised_and_not_retried(self):
        self.fake.error = provider_error("gateway down")
        self.age_cart(now=NOON)
        with at(NOON):
            self.run_command()          # must not raise
            self.run_command()          # failed sends count as handled
        log = self.logs().get()
        self.assertEqual(log.status, NotificationLog.Status.FAILED)
        self.assertIn("gateway down", log.error)
        self.assertEqual(self.logs().count(), 1)

    @override_settings(CART_REMINDER_ENABLED=True, SMS_ENABLED=False)
    def test_global_sms_kill_switch_stops_reminders(self):
        self.age_cart(now=NOON)
        with at(NOON):
            self.run_command()
        self.assertEqual(len(self.fake.sent), 0)
        self.assertEqual(self.logs().count(), 0)
