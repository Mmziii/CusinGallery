"""
Inventory transition (Phase 7 - Payment architecture).

The ONE place stock is decremented for a paid order -- mirroring how
apps/orders/shipping.py is the one place shipping cost is computed.
Nothing else in the codebase writes stock down: checkout deliberately
does NOT reserve or subtract stock (see apps/orders/services.py's
docstring); that's deferred until payment is verified, per the master
spec's flow diagram ("Reduce Inventory" happens *after* "Mark Payment As
Paid").

Exactly-once guarantee: decrement_stock_for_order() is only ever called
from inside apps.payments.services' PENDING -> SUCCESS transition, which
itself runs under a select_for_update() row lock plus the partial unique
constraint unique_successful_payment_per_order. So this function does not
need its own "have I run before" bookkeeping -- the caller's state
transition is the single source of truth for that, and this function
stays a plain, honest "apply these decrements".

Oversell note: because checkout never reserved stock, a concurrent
purchase can have drained a product between checkout and payment
verification. Decrementing below zero would violate the
PositiveIntegerField schema, so we clamp at 0 and log the oversell
loudly for operations to reconcile -- failing the already-accepted
payment would be worse. If true reservation is ever required, it belongs
at checkout, not here.
"""
import logging

from django.conf import settings

from apps.products.models import Product, ProductVariant

logger = logging.getLogger("payments")


def _crossing_label(row, item) -> str:
    """Human-readable Persian label for a low-stock alert line."""
    base = item.product.name
    if item.variant_id is not None:
        return f"{base} (SKU: {row.sku})"
    return base


def decrement_stock_for_order(order) -> None:
    """
    Subtract each OrderItem's quantity from its variant's (or product's)
    stock_quantity. Must be called inside an already-open
    transaction.atomic() (the caller's) so the decrements commit or roll
    back together with the payment-status flip.

    Row locks (select_for_update) serialize concurrent decrements against
    the same catalog row, preventing lost updates if two paid orders for
    the same product verify at the same instant. select_for_update also
    makes calling this OUTSIDE an open transaction a hard
    TransactionManagementError -- a deliberate fail-loud guard against
    someone ever invoking it from a non-atomic context.
    """
    threshold = settings.LOW_STOCK_THRESHOLD
    crossings = []
    for item in order.items.select_related("product", "variant"):
        if item.variant_id is not None:
            target_model, target_id, label = ProductVariant, item.variant_id, f"variant {item.variant_id}"
        else:
            target_model, target_id, label = Product, item.product_id, f"product {item.product_id}"

        row = target_model.objects.select_for_update().get(pk=target_id)
        if row.stock_quantity < item.quantity:
            logger.warning(
                "OVERSELL on paid order %s: %s has %d in stock but the order "
                "requires %d; clamping at 0.",
                order.order_number, label, row.stock_quantity, item.quantity,
            )
        old_stock = row.stock_quantity
        row.stock_quantity = max(0, old_stock - item.quantity)
        row.save(update_fields=["stock_quantity", "updated_at"])
        # Part R4 item 3: a DOWNWARD crossing of the low-stock threshold
        # alerts the owner exactly once per crossing (re-arms only after
        # stock goes back above the threshold).
        if old_stock > threshold >= row.stock_quantity:
            crossings.append((_crossing_label(row, item), row.stock_quantity))
    if crossings:
        from apps.notifications.services import notify_owner_low_stock

        notify_owner_low_stock(order, crossings)


def restore_stock_for_order(order) -> None:
    """
    The exact inverse of decrement_stock_for_order(): hand each
    OrderItem's quantity back to its variant's (or product's)
    stock_quantity. Used when a PAID order is cancelled (its stock was
    decremented at payment verification, so cancelling must give it
    back).

    Like decrement, this must run inside an already-open
    transaction.atomic() with the same row locks, and it deliberately
    has NO "have I run before" bookkeeping of its own: the caller
    (apps/orders/workflow.set_status) owns the exactly-once guarantee
    via Order.stock_restored_at, checked under a lock on the order row.
    """
    for item in order.items.select_related("product", "variant"):
        if item.variant_id is not None:
            target_model, target_id = ProductVariant, item.variant_id
        else:
            target_model, target_id = Product, item.product_id

        row = target_model.objects.select_for_update().get(pk=target_id)
        row.stock_quantity = row.stock_quantity + item.quantity
        row.save(update_fields=["stock_quantity", "updated_at"])

    logger.info("Stock restored for cancelled order %s.", order.order_number)
