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
  takes over (delivered / returned).

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


def validate_transition(current_status, new_status):
    """
    Raise OrderWorkflowError unless ``current_status -> new_status`` is a
    legal edge in the DAG. A no-op transition (same status) is allowed
    and treated as a plain save by callers.
    """
    if new_status == current_status:
        return  # idempotent save with no status change is fine
    if new_status not in allowed_next_statuses(current_status):
        current_label = Order.Status(current_status).label
        new_label = Order.Status(new_status).label
        raise OrderWorkflowError(
            f"Cannot change an order from '{current_label}' to '{new_label}'. "
            f"Allowed next statuses: "
            f"{', '.join(sorted(s.label for s in allowed_next_statuses(current_status))) or 'none (terminal status)'}."
        )


def check_transition(current_status, new_status, tracking_code, shipping_method="standard"):
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
    validate_transition(current_status, new_status)
    if new_status != current_status and new_status == Order.Status.SHIPPED and not tracking_code:
        from . import shipping

        if shipping.get_shipping_methods()[shipping_method].get("requires_address", True):
            raise OrderWorkflowError(
                "Enter the carrier tracking code before marking the order as shipped."
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
            locked.status, new_status, locked.tracking_code, locked.shipping_method
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

        locked.status = new_status
        locked.save(update_fields=["status", "stock_restored_at", "updated_at"])

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
