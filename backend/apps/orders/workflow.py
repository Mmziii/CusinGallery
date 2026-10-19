"""
Order fulfilment workflow (Phase B - Store management).

The ONE place the order status state-machine lives, mirroring how
apps/orders/inventory.py is the one place stock moves and
apps/orders/shipping.py is the one place shipping cost is computed.
The Django admin drives it (see apps/orders/admin.py); nothing else in
the codebase mutates Order.status directly.

Status lifecycle (a strict DAG -- no backwards or skip transitions):

    pending -> confirmed -> processing -> shipped -> delivered
                \\             \\              \\
                 -> cancelled   -> cancelled    -> returned
                                                delivered -> returned

* cancelled and returned are terminal.
* An order can only be cancelled while it is still pre-shipment
  (pending / confirmed / processing). Once shipped, the physical flow
  takes over (delivered / returned). Cancelling is allowed WHETHER OR NOT
  the order was paid -- that is how abandoned unpaid orders are closed.
* Payment gate: «pending -> confirmed» (and every later status) requires
  ``payment_status == PAID``. A paid order deliberately STAYS «در انتظار
  تأیید» until the owner confirms it in the admin -- payment proves the
  money arrived, not that the shop can fulfil the order. See
  apps/payments/services.py, which now only sets payment_status.

Stock restoration on cancel
---------------------------
Stock is decremented ONLY at payment verification (see
apps/orders/inventory.py and apps/payments/services.py). Inside that
same transaction the order is marked payment_status=PAID, so for any
order ``payment_status == PAID`` is exactly equivalent to "stock has
been decremented for this order". Cancelling such an order must hand
the stock back -- exactly once.

Exactly-once is guaranteed two ways, layered:
1. set_status() re-reads the order under select_for_update() inside an
   atomic block, so two concurrent cancel attempts serialize.
2. Order.stock_restored_at records that restoration already happened;
   any later attempt sees it is set and skips the restore. A repeated
   cancel (cancelled -> cancelled) short-circuits as an idempotent
   no-op before any stock logic runs, and cancelled is terminal for
   every OTHER target status.

One documented exception to the PAID-equals-decremented equivalence
(Phase C): if a gateway-verified capture arrives for an order that was
ALREADY cancelled (customer finished paying at the exact moment the
expiry job cancelled the order), apps/payments/services.py records the
real money -- payment SUCCESS, order payment_status=PAID -- WITHOUT
decrementing stock (the order is not being fulfilled) and flags the
order refund-required. No restore can ever fire for it either: the
order is already in a terminal status, which set_status can neither
re-enter nor leave, so exactly-once remains true in both directions.

Refund tracking (Phase C)
-------------------------
Cancelling or returning a PAID order also flags it "refund required"
(apps/orders/refunds.py) -- the money side of the same event the stock
restore handles the goods side. Refunds themselves are manual (PSP
merchant panel) and recorded by the owner in the admin.
"""
from django.db import transaction
from django.utils import timezone

from .inventory import restore_stock_for_order
from .models import Order
from .refunds import flag_refund_required


class OrderWorkflowError(Exception):
    """Raised when a requested status transition is not allowed."""


# Adjacency list of the status DAG. Keys and values use the raw string
# values of Order.Status so this stays readable in logs/errors.
ALLOWED_TRANSITIONS = {
    Order.Status.PENDING: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
    Order.Status.CONFIRMED: {Order.Status.PROCESSING, Order.Status.CANCELLED},
    Order.Status.PROCESSING: {Order.Status.SHIPPED, Order.Status.CANCELLED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED, Order.Status.RETURNED},
    Order.Status.DELIVERED: {Order.Status.RETURNED},
    Order.Status.CANCELLED: set(),
    Order.Status.RETURNED: set(),
}


def allowed_next_statuses(current_status):
    """Return the set of statuses reachable from ``current_status``."""
    return set(ALLOWED_TRANSITIONS.get(current_status, set()))


# Statuses that mean "the shop is actually fulfilling this order". Reaching
# any of them is only honest once the customer's money is in: a paid order
# stays «در انتظار تأیید» until the OWNER confirms it, and an unpaid one
# must never be confirmed, processed, shipped or delivered. Cancelling an
# unpaid order stays allowed -- that is exactly how abandoned ones are
# cleaned up.
FULFILMENT_STATUSES = frozenset(
    {
        Order.Status.CONFIRMED,
        Order.Status.PROCESSING,
        Order.Status.SHIPPED,
        Order.Status.DELIVERED,
    }
)


def requires_payment(status):
    """True when this status may only be entered on a PAID order."""
    return status in FULFILMENT_STATUSES


def payment_block_reason(order=None, new_status=None, payment_status=None):
    """
    Persian explanation of why ``new_status`` is blocked on this order, or
    "" when payment is not an obstacle.

    Accepts either an Order (its payment_status is read) or an explicit
    ``payment_status`` value, so the admin can ask about a transition it
    has not made yet.
    """
    if payment_status is None:
        payment_status = getattr(order, "payment_status", None)
    if new_status is None or not requires_payment(new_status):
        return ""
    if payment_status == Order.PaymentStatus.PAID:
        return ""
    return (
        "این سفارش پرداخت نشده است؛ تا زمانی که پرداخت آن تأیید نشود نمی‌توان آن را "
        f"به «{Order.Status(new_status).label}» برد. "
        "برای سفارش پرداخت‌نشده فقط «لغو شده» مجاز است."
    )


def validate_transition(current_status, new_status, payment_status=None):
    """
    Raise OrderWorkflowError unless ``current_status -> new_status`` is a
    legal edge in the DAG. A no-op transition (same status) is allowed
    and treated as a plain save by callers.

    ``payment_status`` is the order's payment status. When given, a
    fulfilment status (confirmed and beyond) is refused unless the order
    is PAID; cancelling is never blocked by payment.
    """
    if new_status == current_status:
        return  # idempotent save with no status change is fine
    if new_status not in allowed_next_statuses(current_status):
        current_label = Order.Status(current_status).label
        new_label = Order.Status(new_status).label
        allowed_labels = sorted(
            s.label for s in allowed_next_statuses(current_status)
        )
        raise OrderWorkflowError(
            f"طبق گردش کار سفارش نمی‌توان وضعیت را از «{current_label}» به "
            f"«{new_label}» برد. "
            + (
                f"وضعیت‌های مجاز پس از «{current_label}»: "
                f"{'، '.join(allowed_labels)}."
                if allowed_labels
                else f"«{current_label}» وضعیت پایانی است و وضعیت بعدی ندارد."
            )
        )
    reason = payment_block_reason(new_status=new_status, payment_status=payment_status)
    if reason:
        raise OrderWorkflowError(reason)


def check_transition(current_status, new_status, tracking_code, shipping_method="standard",
                     payment_status=None):
    """
    Full pre-save validation for moving an order from ``current_status``
    to ``new_status``: the DAG plus business preconditions (a courier-
    shipped order must carry a tracking code -- ``tracking_code`` is the
    value that will be on the order after the save, so callers pass the
    incoming form value). Pickup orders are the exception: there is no
    carrier, so no tracking code is required (Part 1; "shipped" then
    means "ready for pickup"). Raises OrderWorkflowError on any
    violation, returns None when the move is legal.

    Admin runs this BEFORE saving anything so an invalid move persists
    nothing; set_status runs it again under the row lock as a safety
    net against concurrent edits.
    """
    validate_transition(current_status, new_status, payment_status=payment_status)
    if new_status != current_status and new_status == Order.Status.SHIPPED and not tracking_code:
        from . import shipping

        if shipping.get_shipping_methods()[shipping_method].get("requires_address", True):
            raise OrderWorkflowError(
                "پیش از ثبت وضعیت «ارسال شده»، کد رهگیری مرسوله را وارد کنید."
            )


def set_status(order, new_status):
    """
    Transition ``order`` to ``new_status``, enforcing the DAG and
    restoring stock exactly once when a paid order is cancelled.

    Must be given an Order instance (its pk is used to re-lock the row).
    Returns the refreshed, locked instance. Runs in its own atomic block
    so the stock restore commits or rolls back together with the status
    change.
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status == new_status:
            return locked  # no-op: nothing to change, nothing to restore

        check_transition(
            locked.status, new_status, locked.tracking_code, locked.shipping_method,
            payment_status=locked.payment_status,
        )

        cancelled_a_paid_order = (
            new_status == Order.Status.CANCELLED
            and locked.payment_status == Order.PaymentStatus.PAID
        )
        if cancelled_a_paid_order and locked.stock_restored_at is None:
            restore_stock_for_order(locked)
            locked.stock_restored_at = timezone.now()

        # Refund tracking (Phase C): cancelling or returning a PAID order
        # means the shop is holding the customer's money for an order it
        # will not deliver -- flag it "refund required" so it appears in
        # the owner's refund filter until the manual PSP refund is done
        # and recorded (apps/orders/refunds.py). Fires at most once per
        # order: cancelled and returned are terminal, and the no-op
        # short-circuit above stops repeat transitions. Stock and refund
        # are independent effects: stock moves only on CANCEL (a returned
        # order's goods come back through the physical return flow), the
        # refund flag moves on both.
        returned_a_paid_order = (
            new_status == Order.Status.RETURNED
            and locked.payment_status == Order.PaymentStatus.PAID
        )
        if cancelled_a_paid_order or returned_a_paid_order:
            action = "لغو" if cancelled_a_paid_order else "مرجوع"
            flag_refund_required(
                locked,
                amount=locked.total,
                note=f"{action} سفارش پرداخت‌شده — کل مبلغ باید به مشتری بازگردانده شود.",
            )

        expired_pending_payment = False
        if new_status == Order.Status.CANCELLED:
            # Stop showing an in-flight gateway attempt after its order has
            # been cancelled. The callback still recognizes this marker so
            # a genuinely late capture can be recorded and refunded.
            from apps.payments.models import Payment

            expired_pending_payment = Payment.objects.filter(
                order=locked, status=Payment.Status.PENDING
            ).update(
                status=Payment.Status.FAILED,
                failure_reason="Order cancelled before payment completed",
                updated_at=timezone.now(),
            ) > 0
            if locked.payment_status == Order.PaymentStatus.PENDING:
                locked.payment_status = Order.PaymentStatus.FAILED

        locked.status = new_status
        fields = ["status", "stock_restored_at", "updated_at"]
        if expired_pending_payment or locked.payment_status == Order.PaymentStatus.FAILED:
            fields.append("payment_status")
        locked.save(update_fields=fields)

        if new_status == Order.Status.CONFIRMED:
            # The shop has accepted the order -- only NOW is it fair to
            # tell the customer it was confirmed. Payment alone only earns
            # the «در انتظار تأیید» state (see apps/payments/services.py,
            # which fires Events.ORDER_PAID instead).
            from apps.notifications.services import Events, notify_order_event

            notify_order_event(locked, Events.ORDER_CONFIRMED)

        if new_status == Order.Status.SHIPPED:
            # Customer "shipped" notification with the tracking code
            # (Phase D). Queued via transaction.on_commit inside
            # apps/notifications: nothing is sent if this transition
            # rolls back, provider/SMTP failures are contained there and
            # can never break the admin status change, and repeat
            # SHIPPED saves are idempotent (the no-op short-circuit above
            # plus the NotificationLog unique constraint).
            from apps.notifications.services import Events, notify_order_event

            notify_order_event(locked, Events.ORDER_SHIPPED)

        return locked
