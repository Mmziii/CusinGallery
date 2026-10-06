"""
Expire abandoned unpaid orders (Phase C - Real payments).

    python manage.py expire_unpaid_orders [--hours N] [--dry-run]

Cancels orders that were created more than N hours ago (default:
settings.ORDER_EXPIRY_HOURS, from the ORDER_EXPIRY_HOURS env var) and
never got paid -- the customer checked out, was redirected to the
gateway, and never came back. Designed to be pointed at by cron and run
as often as desired.

Why this is safe to run repeatedly:

  * Selection is narrow: only status=pending orders whose
    payment_status is unpaid/pending/failed and whose created_at is
    older than the cutoff. Paid, confirmed, shipped, delivered and
    terminal (cancelled/returned) orders are never selected.
  * Every candidate is RE-CHECKED under its own row lock
    (select_for_update) immediately before cancelling: an order that
    got paid or advanced between the queryset read and the cancel is
    skipped, never cancelled.
  * Cancelling goes through apps/orders/workflow.set_status -- the same
    single mechanism the admin uses -- so the status DAG and all money/
    stock rules behave exactly as they do there. For these orders that
    means NO stock movement (stock is only ever decremented at payment
    verification, and these orders were never paid) and no refund flag
    (no money was captured).
  * The run is idempotent: a second invocation immediately afterwards
    finds nothing to do.

The one race that cannot be locked away -- a customer sitting on the
gateway page who completes payment for an order a microsecond after
this command cancelled it -- is handled by the payment callback, not
here: apps/payments/services.py records the verified capture and flags
the order refund-required, so the money is never lost. Stale PENDING
payment attempts are deliberately left PENDING for exactly that reason:
pre-marking them cancelled would blind the callback's verified-capture
path to real money.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.workflow import OrderWorkflowError, set_status

logger = logging.getLogger("payments")

#: payment_status values that mean "this order's money never arrived".
#: PENDING is included: an in-flight gateway attempt on an order this
#: old is abandoned by definition (gateway authorities expire long
#: before the default cutoff), and the late-capture path in
#: apps/payments/services.py covers the customer who pays anyway.
UNPAID_STATUSES = (
    Order.PaymentStatus.UNPAID,
    Order.PaymentStatus.PENDING,
    Order.PaymentStatus.FAILED,
)


class Command(BaseCommand):
    help = (
        "Cancel unpaid orders older than --hours (default: settings.ORDER_EXPIRY_HOURS). "
        "Never moves stock -- stock is only taken at payment -- and is safe to run "
        "repeatedly from cron."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=None,
            help="Age threshold in hours (default: ORDER_EXPIRY_HOURS setting, "
                 f"currently {settings.ORDER_EXPIRY_HOURS}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the orders that WOULD be cancelled without changing anything.",
        )

    def handle(self, *args, **options):
        hours = options["hours"] if options["hours"] is not None else settings.ORDER_EXPIRY_HOURS
        if hours <= 0:
            raise CommandError("--hours must be a positive number of hours.")
        cutoff = timezone.now() - timedelta(hours=hours)
        dry_run = options["dry_run"]

        candidates = (
            Order.objects.filter(
                status=Order.Status.PENDING,
                payment_status__in=UNPAID_STATUSES,
                created_at__lt=cutoff,
            )
            .order_by("pk")
        )

        if dry_run:
            count = 0
            for order in candidates.iterator(chunk_size=200):
                count += 1
                self.stdout.write(
                    f"WOULD CANCEL {order.order_number} "
                    f"(created {timezone.localtime(order.created_at):%Y-%m-%d %H:%M}, "
                    f"payment_status={order.payment_status})"
                )
            self.stdout.write(
                f"Dry run: {count} unpaid order(s) older than {hours}h would be "
                f"cancelled; nothing was changed."
            )
            return

        cancelled = 0
        skipped = 0
        for order in candidates.iterator(chunk_size=200):
            try:
                if self._cancel_if_still_unpaid(order.pk, cutoff):
                    cancelled += 1
                    self.stdout.write(f"CANCELLED {order.order_number} (unpaid, older than {hours}h)")
                else:
                    skipped += 1
            except OrderWorkflowError as exc:  # pragma: no cover - re-check makes this near-impossible
                skipped += 1
                logger.error("expire_unpaid_orders: could not cancel order %s: %s", order.order_number, exc)

        summary = (
            f"expire_unpaid_orders: cancelled {cancelled} unpaid order(s) older than "
            f"{hours}h" + (f", skipped {skipped} that changed state mid-run" if skipped else "") + "."
        )
        self.stdout.write(summary)
        logger.info(summary)

    @staticmethod
    def _cancel_if_still_unpaid(order_pk, cutoff) -> bool:
        """
        Re-check the expiry conditions under the order's row lock and
        cancel it atomically. Returns True only if THIS call cancelled
        the order; False means the order changed state between the
        queryset read and the lock (paid, advanced, or somehow younger
        than the cutoff) and was left completely alone.
        """
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order_pk)
            if (
                locked.status != Order.Status.PENDING
                or locked.payment_status not in UNPAID_STATUSES
                or locked.created_at >= cutoff
            ):
                return False
            # The single status mechanism: DAG-checked, and for these
            # never-paid orders it moves no stock and flags no refund.
            set_status(locked, Order.Status.CANCELLED)
            return True
