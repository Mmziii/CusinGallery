"""
Notification audit log (Phase D - Notifications).

One row per delivery ATTEMPT of one event over one channel. This is the
owner's/developer's answer to "did we tell the customer, and what
happened?" -- and the idempotency backstop: the partial unique
constraint on (event, order, channel) makes "never send the same event
twice for the same order" a database-level guarantee, not just a
service-layer check (services.py creates the row BEFORE sending, so
concurrent deliveries of one event cannot both get out).

Recipients are stored MASKED (see services.mask_phone / mask_email):
this table is operational audit data, not a place to accumulate raw
personal contact info -- the raw phone/email already live on the
account/order rows that this references.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class NotificationLog(TimeStampedModel):
    class Channel(models.TextChoices):
        SMS = "sms", "پیامک"
        EMAIL = "email", "ایمیل"
        # Part R4 item 3: messenger bots (Telegram/Bale) for OWNER alerts.
        MESSENGER = "messenger", "پیام‌رسان"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار ارسال"
        SENT = "sent", "ارسال شد"
        FAILED = "failed", "ناموفق"
        SKIPPED = "skipped", "رد شده"

    event = models.CharField(
        "رویداد", max_length=40,
        help_text="Machine name of the event, e.g. order_confirmed / order_shipped / "
        "password_reset. See apps/notifications/services.py Events.",
    )
    channel = models.CharField("کانال", max_length=10, choices=Channel.choices)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)

    # Both nullable: order events reference the order (and its owner),
    # password-reset events reference only the user. SET_NULL keeps the
    # audit row even if the referenced object is ever removed.
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notification_logs", verbose_name="سفارش",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notification_logs", verbose_name="کاربر",
    )

    recipient_masked = models.CharField(
        "گیرنده (ماسک‌شده)", max_length=120,
        help_text="Phone/email of the recipient, masked -- raw contact data is never "
        "duplicated into the audit log.",
    )
    error = models.TextField("خطا", blank=True, default="")
    provider_message_id = models.CharField(
        "شناسهٔ پیام نزد ارائه‌دهنده", max_length=64, blank=True, default="",
    )

    class Meta:
        verbose_name = "گزارش اعلان"
        verbose_name_plural = "گزارش اعلان‌ها"
        ordering = ["-created_at"]
        constraints = [
            # The idempotency backstop: one delivery record per
            # (event, order, channel). Services create the row BEFORE
            # sending, so a duplicate/concurrent delivery attempt hits
            # this and is skipped. Password-reset events have no order
            # and are deliberately exempt (each request is a new,
            # separately rate-limited event).
            models.UniqueConstraint(
                fields=["event", "order", "channel"],
                condition=Q(order__isnull=False),
                name="unique_notification_per_event_order_channel",
            ),
        ]
        indexes = [
            models.Index(fields=["event", "status"]),
            models.Index(fields=["order"]),
        ]

    def __str__(self):
        target = self.order.order_number if self.order_id else (self.event)
        return f"{target} / {self.event} / {self.channel} -> {self.status}"
