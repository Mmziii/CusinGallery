"""
Refund tracking (Phase C - Real payments).

The ONE place Order.refund_* fields are written -- the refund counterpart
of apps/orders/inventory.py for stock. Three callers, no others:

    apps/orders/workflow.set_status
        a PAID order is cancelled or returned -> the customer's money must
        go back; flag_refund_required() marks it.

    apps/payments/services.handle_callback
        a gateway-verified capture that can no longer be applied to its
        order (late success after auto-cancellation, or a second attempt
        that verified after another already paid the order = duplicate
        capture) is REAL money -> flag_refund_required() marks it.

    Django admin (apps/orders/admin.py)
        the owner executed the refund manually in the PSP's merchant
        panel (there is deliberately NO automatic refund integration) and
        records it here: finalize_refunded() on the change form, or
        mark_refunded() programmatically. A note/reference is REQUIRED --
        it is the audit trail of an out-of-system money movement.

State machine:

    none      -> required    flag_refund_required()   (system-driven)
    required  -> required    flag_refund_required() again: amounts
                             ACCUMULATE (e.g. a full-order refund plus a
                             duplicate capture each add their own sum)
    required  -> refunded    owner action, note mandatory
    refunded  -> required    flag_refund_required() ONLY: new verified
                             money after a completed refund must never be
                             hidden. The admin refuses manual regressions
                             (validate_admin_refund_change).

refund_reference is an append-only journal (one line per event) so the
full money story of an order survives every transition.
"""
import logging

from django.utils import timezone

from .models import Order

logger = logging.getLogger("payments")


class RefundError(Exception):
    """Raised for invalid refund bookkeeping requests (owner-facing)."""


def _append_note(order, note: str) -> None:
    note = (note or "").strip()
    if not note:
        return
    existing = (order.refund_reference or "").strip()
    order.refund_reference = f"{existing}\n{note}" if existing else note


def flag_refund_required(order, amount: int, note: str = "") -> Order:
    """
    Flag that `amount` Toman of gateway-verified money on this order owes
    the customer a refund. Accumulating: repeated calls add up (each call
    represents a distinct money event). Saves ONLY the refund fields.

    Callers must hold the order row lock (select_for_update inside an
    atomic block) -- both call sites do, so this read-modify-write is
    serialized exactly like the stock transitions in inventory.py.
    """
    if amount is None or amount <= 0:
        # Never silently swallow this: it means a caller has a bug, and
        # the alternative (flagging 0 Toman) would hide real money.
        logger.error(
            "flag_refund_required called with non-positive amount %r for order %s; ignoring.",
            amount, order.order_number,
        )
        return order

    order.refund_status = Order.RefundStatus.REQUIRED
    order.refund_amount = (order.refund_amount or 0) + amount
    _append_note(order, note)
    order.save(update_fields=["refund_status", "refund_amount", "refund_reference", "updated_at"])
    logger.warning(
        "Order %s flagged REFUND REQUIRED: +%s Toman (total flagged: %s). %s",
        order.order_number, amount, order.refund_amount, note,
    )
    return order


def _apply_refunded(order, previous_status: str, previous_reference: str) -> None:
    """
    Shared invariants of "this refund was executed", used by both the
    admin-form path (finalize_refunded) and the programmatic path
    (mark_refunded):

      * something must actually have been flagged before (NONE -> refunded
        is not a thing an owner can invent here),
      * the note journal must have GROWN -- an empty or unchanged
        refund_reference means no audit trail for the manual money
        movement, so it is refused,
      * refunded_at is stamped by the system, never typed,
      * a PAID order's payment_status becomes REFUNDED (the money story
        of the order: paid -> refunded). Anything else (e.g. a late
        capture on an already-cancelled order that never showed PAID to
        the customer) is left alone on purpose.
    """
    if previous_status == Order.RefundStatus.NONE:
        raise RefundError(
            "This order has no flagged refund. A refund becomes required when a paid "
            "order is cancelled/returned (or flag it manually as 'required' first)."
        )
    new_reference = (order.refund_reference or "").strip()
    if not new_reference or new_reference == (previous_reference or "").strip():
        raise RefundError(
            "Enter the refund note/reference (e.g. the PSP panel's refund code) "
            "before marking the order as refunded."
        )
    order.refund_status = Order.RefundStatus.REFUNDED
    order.refunded_at = timezone.now()
    if order.payment_status == Order.PaymentStatus.PAID:
        order.payment_status = Order.PaymentStatus.REFUNDED


def finalize_refunded(order, db_obj) -> Order:
    """
    Admin change-form path: `order` carries the owner's edited form values
    (refund_reference = journal + the new note they typed), `db_obj` is
    the persisted row. Validates and completes the refund on `order` but
    does NOT save -- the admin's save persists everything in one write.
    """
    _apply_refunded(order, db_obj.refund_status, db_obj.refund_reference)
    return order


def mark_refunded(order, note: str, amount=None) -> Order:
    """
    Programmatic path: appends `note` to the journal, optionally corrects
    the amount, completes the refund and saves. This is the function tests
    and any future tooling use; the admin form goes through
    finalize_refunded instead because there the note arrives already
    merged into the journal textarea.
    """
    if not (note or "").strip():
        raise RefundError("A refund note/reference is required to mark an order refunded.")
    previous_status = order.refund_status
    previous_reference = order.refund_reference
    _append_note(order, note)
    if amount is not None:
        order.refund_amount = amount
    _apply_refunded(order, previous_status, previous_reference)
    order.save(update_fields=[
        "refund_status", "refund_amount", "refund_reference",
        "refunded_at", "payment_status", "updated_at",
    ])
    logger.info(
        "Order %s marked REFUNDED: %s Toman. Note: %s",
        order.order_number, order.refund_amount, note,
    )
    return order


def validate_admin_refund_change(db_obj, new_status: str) -> None:
    """
    Pre-save validation of a manual refund_status change submitted through
    the admin change form (the -> refunded case is validated inside
    finalize_refunded, which needs the edited reference too). Raises
    RefundError; the admin turns that into a ValidationError so NOTHING
    is persisted on an invalid move -- same fail-closed rule as the
    order-status DAG.
    """
    old_status = db_obj.refund_status
    if new_status == old_status:
        return
    if new_status == Order.RefundStatus.REQUIRED:
        if old_status == Order.RefundStatus.REFUNDED:
            raise RefundError(
                "A completed refund cannot be moved back to 'required'. New money "
                "events are flagged by the system automatically."
            )
        return
    if new_status == Order.RefundStatus.NONE:
        raise RefundError(
            "Refund state cannot be cleared once flagged -- it is part of the "
            "financial audit trail. Correct the amount/note instead."
        )
