"""
Payments models (Phase 7 - Payment architecture).

One Payment row per gateway attempt -- an order may accumulate several
over its lifetime (a cancelled attempt, a failed attempt, a retry, and
finally the successful one), but at most ONE of them is ever in
Status.SUCCESS, enforced at the database level (see Meta.constraints):
the partial unique index is the final backstop behind which inventory
decrement happens exactly once, even if two different attempts for the
same order somehow both verified successfully at the same instant.

Snapshot discipline, same reasoning as Order's own address/totals
snapshots (apps/orders/models.py): `amount` copies the order total at
initiation time rather than dereferencing order.total later, so the
payment record stays historically correct even if the order's totals
were ever adjusted afterwards, and verify-time code compares against a
value that was fixed when the customer was actually sent to pay.
"""
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel
from apps.orders.models import Order


class Payment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        SUCCESS = "success", "موفق"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغو شده"

    # PROTECT (not CASCADE): a payment record is part of the financial
    # audit trail and must never disappear just because someone deletes
    # an order row -- same audit-trail reasoning CouponUsage uses.
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")

    amount = models.PositiveBigIntegerField(
        help_text="The order total captured at payment initiation (Toman). Verification "
        "compares against this, never against a client-supplied value.",
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    gateway = models.CharField(
        max_length=40,
        help_text="Identifier of the gateway implementation used for this attempt "
        "(settings.PAYMENT_GATEWAY at initiation time).",
    )
    gateway_transaction_id = models.CharField(
        max_length=128, blank=True, default="",
        help_text="The gateway's own transaction handle (e.g. an 'authority' code). "
        "Callback handling looks the payment up by this, never by our own id.",
    )
    gateway_ref_id = models.CharField(
        max_length=128, blank=True, default="",
        help_text="The gateway's final verification reference (receipt id), set only "
        "after a successful verify call.",
    )
    failure_reason = models.CharField(max_length=255, blank=True, default="")

    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت‌ها"
        ordering = ["-created_at"]
        constraints = [
            # At most one successful payment per order. The service layer
            # already transitions only PENDING -> SUCCESS under a row
            # lock; this is the database-level backstop that makes
            # "inventory decremented exactly once" true even against
            # exotic races (two distinct attempts verifying at once).
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status="success"),
                name="unique_successful_payment_per_order",
            ),
        ]
        indexes = [
            models.Index(fields=["gateway_transaction_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["order", "status"]),
        ]

    def __str__(self):
        return f"Payment #{self.pk} for {self.order} ({self.get_status_display()})"
