"""
Part R5 item 11: opt-in abandoned-cart reminder SMS.

    python manage.py send_cart_reminders [--dry-run]

Run hourly by the production scheduler service (docker-compose.prod.yml).
Sends at most ONE reminder per eligible cart, to logged-in customers who
explicitly opted in (User.marketing_sms_consent, default off), for a
server cart that has sat untouched for CART_REMINDER_AFTER_HOURS
(default 24), and only when:

  * CART_REMINDER_ENABLED=True      (default False -- feature is OFF)
  * SMS_ENABLED=True                (global SMS kill-switch)
  * the cart is non-empty and its newest change is older than the cutoff
  * the customer has placed NO order since that cart change
  * this exact cart state was never reminded before (one reminder per
    cart state; the state fingerprint lives in the NotificationLog
    event name: cart_reminder_<16-hex>)
  * the last reminder to this customer is older than
    CART_REMINDER_COOLDOWN_DAYS (default 7)
  * Tehran local time is between 09:00 and 21:00 (quiet hours
    21:00-09:00 send nothing; nothing is "consumed" during quiet hours)

The message always contains a plain-Persian opt-out instruction. Every
send is recorded in NotificationLog BEFORE delivery (sent/failed); a
provider failure is logged and never raises, and is treated as handled
(no retry-spamming of broken numbers).
"""
import hashlib
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cart.models import Cart
from apps.notifications.models import NotificationLog
from apps.notifications.providers import get_provider
from apps.notifications.services import mask_phone
from apps.orders.models import Order

logger = logging.getLogger("notifications")

EVENT_PREFIX = "cart_reminder_"
TEHRAN = ZoneInfo("Asia/Tehran")


def cart_state(cart):
    """Return (state_time, fingerprint) for a cart.

    state_time is the newest of the cart row and its items (any item
    add/remove/quantity change bumps an item's updated_at). The
    fingerprint hashes the exact line set, so the SAME reminder is never
    sent twice for the same cart contents -- but editing the cart and
    abandoning it again is a NEW state and may be reminded once more
    (subject to the per-customer cooldown).
    """
    rows = list(cart.items.values_list("product_id", "variant_id", "quantity", "updated_at"))
    state_time = cart.updated_at
    for _, _, _, updated_at in rows:
        if updated_at and updated_at > state_time:
            state_time = updated_at
    basis = "|".join(
        sorted(f"{product_id}:{variant_id}:{quantity}" for product_id, variant_id, quantity, _ in rows)
    )
    fingerprint = hashlib.md5(basis.encode("utf-8")).hexdigest()[:16]
    return state_time, fingerprint


def reminder_message(user):
    name = (user.first_name or "").strip()
    greeting = f"{name} عزیز، " if name else ""
    return (
        f"{greeting}کالاهای سبد خرید شما در کازین گالری هنوز منتظر شماست. "
        f"برای تکمیل خرید: {settings.FRONTEND_URL}/cart/ . "
        "برای عدم دریافت این پیام‌ها، گزینهٔ «پیامک تبلیغاتی» را در حساب کاربری خود خاموش کنید."
    )


class Command(BaseCommand):
    help = (
        "Send opt-in abandoned-cart reminder SMS (CART_REMINDER_ENABLED gate, "
        "consent required, quiet hours 21:00-09:00 Tehran, one reminder per "
        "cart state, per-customer cooldown)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report who would be reminded without sending or logging anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if not settings.CART_REMINDER_ENABLED:
            self.stdout.write("Cart reminders disabled (CART_REMINDER_ENABLED is off). Nothing to do.")
            return
        if not settings.SMS_ENABLED:
            self.stdout.write("SMS globally disabled (SMS_ENABLED is off). Nothing to do.")
            return

        now = timezone.now()
        now_tehran = now.astimezone(TEHRAN)
        if not (9 <= now_tehran.hour < 21):
            self.stdout.write(
                f"Quiet hours in Tehran ({now_tehran.strftime('%H:%M')}); nothing sent."
            )
            return

        cutoff = now - timedelta(hours=settings.CART_REMINDER_AFTER_HOURS)
        cooldown = timedelta(days=settings.CART_REMINDER_COOLDOWN_DAYS)

        carts = (
            Cart.objects.filter(items__isnull=False, user__marketing_sms_consent=True)
            .exclude(user__phone__isnull=True)
            .exclude(user__phone="")
            .select_related("user")
            .distinct()
        )

        sent = skipped = 0
        for cart in carts:
            state_time, fingerprint = cart_state(cart)
            user = cart.user

            if state_time > cutoff:
                skipped += 1  # cart is still fresh
                continue
            if Order.objects.filter(user=user, created_at__gt=state_time).exists():
                skipped += 1  # they came back and ordered already
                continue

            event = EVENT_PREFIX + fingerprint
            if NotificationLog.objects.filter(
                user=user, event=event, channel=NotificationLog.Channel.SMS
            ).exists():
                skipped += 1  # this exact cart state was already reminded
                continue

            last = (
                NotificationLog.objects.filter(
                    user=user,
                    event__startswith=EVENT_PREFIX,
                    channel=NotificationLog.Channel.SMS,
                )
                .order_by("-created_at")
                .first()
            )
            if last is not None and last.created_at > now - cooldown:
                skipped += 1  # inside the per-customer cooldown window
                continue

            if dry_run:
                self.stdout.write(
                    f"Would remind {mask_phone(user.phone)} (cart state {fingerprint})."
                )
                sent += 1
                continue

            # Log BEFORE sending (same shape as the order-notification
            # path): the audit row exists no matter what happens next.
            log = NotificationLog.objects.create(
                event=event,
                channel=NotificationLog.Channel.SMS,
                status=NotificationLog.Status.PENDING,
                user=user,
                recipient_masked=mask_phone(user.phone),
            )
            try:
                message_id = get_provider().send(user.phone, message=reminder_message(user))
                log.status = NotificationLog.Status.SENT
                log.provider_message_id = message_id
                sent += 1
            except Exception as exc:  # provider failures never break the run
                log.status = NotificationLog.Status.FAILED
                log.error = str(exc)[:2000]
                logger.error(
                    "cart-reminder SMS failed for user %s (%s): %s",
                    user.pk, mask_phone(user.phone), exc,
                )
            log.save()

        self.stdout.write(
            self.style.SUCCESS(f"Cart reminders done: {sent} sent, {skipped} skipped.")
        )
