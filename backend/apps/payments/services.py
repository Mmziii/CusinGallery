"""
Payment business logic (Phase 7 - Payment architecture).

Same service/view split as apps.cart and apps.orders: this module owns
validation and state transitions; views.py is thin HTTP orchestration.

The two entry points:

    initiate_payment(user, order_id)
        Customer wants to pay for one of their own unpaid orders.
        Validates ownership + payability, creates a Payment attempt, and
        asks the configured gateway for a redirect URL.

    handle_callback(callback_data)
        The gateway sent the customer's browser back. Looks the attempt
        up by the GATEWAY's transaction id (never our own id -- the
        client supplies only what the gateway gave it), asks the gateway
        to VERIFY the outcome, and applies exactly one of these
        transitions inside a locked transaction:

            PENDING -> SUCCESS    order paid, status confirmed,
                                  inventory decremented exactly once,
                                  coupon usage recorded (if any)
            PENDING -> FAILED     gateway declined / verification failed
            PENDING -> CANCELLED  customer cancelled at the gateway page

Idempotency: a callback for an attempt that already reached SUCCESS
returns that payment unchanged -- no second inventory decrement, no
duplicate usage records. The row lock (select_for_update) serializes
concurrent callbacks for the same attempt, and the partial unique
constraint unique_successful_payment_per_order is the final backstop
against two different attempts for one order both succeeding.
"""
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.orders.models import Order

from .gateways import GatewayError, get_gateway
from .models import Payment

logger = logging.getLogger("payments")


class PaymentError(Exception):
    """
    Raised for payment business-rule violations. Carries (errors,
    http_status) so views can translate directly into an API response,
    same convention as apps.cart.services.CartError /
    apps.orders.services.CheckoutError -- except those only ever map to
    400, while payment initiation can legitimately fail with 404 (not
    this user's order) or 409 (already paid).
    """

    def __init__(self, errors, http_status=400):
        self.errors = errors
        self.http_status = http_status
        super().__init__(str(errors))


def initiate_payment(user, order_id, callback_url=None) -> dict:
    """
    Creates a PENDING payment attempt for one of the user's own payable
    orders and returns {payment, redirect_url}. Never trusts anything
    from the client beyond "which of my orders" -- the amount is always
    re-read from the order row itself.

    `callback_url` is the absolute URL of this backend's callback
    endpoint, supplied by the view from the incoming request so it's
    correct on whatever origin serves the API; falls back to
    settings.PAYMENT_CALLBACK_URL.
    """
    try:
        order = Order.objects.get(pk=order_id, user=user)
    except (Order.DoesNotExist, ValueError, TypeError):
        # Ownership and existence collapse into one 404 -- another user's
        # order must not be distinguishable from a nonexistent one, same
        # pattern as every other ownership-scoped endpoint in this project.
        raise PaymentError({"order": ["Order not found."]}, http_status=404)

    if order.payment_status == Order.PaymentStatus.PAID:
        raise PaymentError({"order": ["This order is already paid."]}, http_status=409)
    if order.status == Order.Status.CANCELLED:
        raise PaymentError({"order": ["A cancelled order cannot be paid."]}, http_status=409)

    gateway = get_gateway()

    with transaction.atomic():
        payment = Payment.objects.create(
            order=order,
            amount=order.total,
            gateway=gateway.name,
            status=Payment.Status.PENDING,
        )
        # The order is now mid-payment: not paid yet, but no longer a
        # plain unpaid order either. A failed/cancelled attempt moves it
        # back (FAILED/UNPAID) in handle_callback.
        order.payment_status = Order.PaymentStatus.PENDING
        order.save(update_fields=["payment_status", "updated_at"])

    # Gateway interaction OUTSIDE the atomic block: a slow/unreachable
    # gateway must not hold a database transaction open, and if it fails
    # the attempt is simply recorded as failed.
    effective_callback_url = callback_url or settings.PAYMENT_CALLBACK_URL
    try:
        result = gateway.initiate(payment, effective_callback_url)
    except GatewayError as exc:
        payment.status = Payment.Status.FAILED
        payment.failure_reason = str(exc)[:255]
        payment.save(update_fields=["status", "failure_reason", "updated_at"])
        order.payment_status = Order.PaymentStatus.UNPAID
        order.save(update_fields=["payment_status", "updated_at"])
        logger.error("Gateway initiation failed for payment %s: %s", payment.pk, exc)
        raise PaymentError(
            {"gateway": ["The payment gateway is unavailable. Please try again later."]},
            http_status=502,
        )

    payment.gateway_transaction_id = result.gateway_transaction_id
    payment.save(update_fields=["gateway_transaction_id", "updated_at"])

    return {"payment": payment, "redirect_url": result.redirect_url}


def handle_callback(callback_data: dict) -> Payment:
    """
    Processes a gateway callback. Returns the resulting Payment.
    Raises PaymentError for callbacks that don't correspond to any known
    attempt (unknown/missing transaction id) -- the view turns that into
    a redirect to the frontend's failure page, never a 500.
    """
    gateway = get_gateway()

    # First, resolve which attempt this callback is for, WITHOUT holding
    # any lock -- verification may involve work we don't want to do under
    # a row lock, and an unknown callback must not block anything.
    raw_authority = callback_data.get("authority") or ""
    if isinstance(raw_authority, (list, tuple)):  # tolerate ?authority=a&authority=b
        raw_authority = raw_authority[0] if raw_authority else ""
    gateway_transaction_id = str(raw_authority).strip()
    if not gateway_transaction_id:
        raise PaymentError({"callback": ["Missing gateway transaction reference."]}, http_status=400)

    try:
        payment = Payment.objects.select_related("order").get(
            gateway_transaction_id=gateway_transaction_id
        )
    except Payment.DoesNotExist:
        raise PaymentError({"callback": ["Unknown gateway transaction reference."]}, http_status=404)
    except Payment.MultipleObjectsReturned:  # pragma: no cover - index makes this near-impossible
        logger.error("Duplicate gateway_transaction_id %s", gateway_transaction_id)
        raise PaymentError({"callback": ["Ambiguous gateway transaction reference."]}, http_status=400)

    # Idempotency fast path: an attempt that already left PENDING is
    # terminal. A SUCCESS obviously must never be re-processed (that's
    # what makes duplicate callbacks safe -- no second inventory
    # decrement, ever), and a FAILED/CANCELLED attempt must never be
    # flipped to SUCCESS afterwards either -- real gateways void an
    # authority once it fails or is cancelled, and a retry always gets a
    # fresh attempt with its own authority (see initiate_payment).
    if payment.status != Payment.Status.PENDING:
        return payment

    # Ask the gateway itself whether this callback is genuine and what it
    # means -- never trust the raw parameters alone.
    verification = gateway.verify(payment, callback_data)

    with transaction.atomic():
        # Re-read under the lock: another callback may have completed the
        # transition between our fast-path check and here.
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.status != Payment.Status.PENDING:
            return locked

        if verification.success:
            return _complete_successful_payment(locked, verification.gateway_ref_id)

        if verification.cancelled:
            locked.status = Payment.Status.CANCELLED
            locked.failure_reason = verification.failure_reason[:255]
            locked.save(update_fields=["status", "failure_reason", "updated_at"])
            # The order simply goes back to payable -- nothing happened.
            _set_order_payment_status(locked.order, Order.PaymentStatus.UNPAID)
            return locked

        locked.status = Payment.Status.FAILED
        locked.failure_reason = verification.failure_reason[:255]
        locked.save(update_fields=["status", "failure_reason", "updated_at"])
        _set_order_payment_status(locked.order, Order.PaymentStatus.FAILED)
        return locked


def _complete_successful_payment(payment: Payment, gateway_ref_id: str = "") -> Payment:
    """
    The single code path in which an order becomes paid. Everything that
    must happen exactly once per paid order lives inside the caller's
    atomic block, under the caller's row lock:

        payment  PENDING -> SUCCESS (+ ref id, paid_at)
        order    payment_status -> PAID, status -> CONFIRMED
        stock    decremented via apps.orders.inventory
        coupon   usage recorded (if the order used one)

    The partial unique constraint on successful payments is the final
    guard: if some exotic race ever got two attempts here for one order,
    the second insert/update raises IntegrityError and the whole
    transaction rolls back rather than double-paying.
    """
    order = payment.order

    # Amount integrity: the payment was initiated for order.total; if the
    # order row no longer matches that snapshot, something is very wrong
    # (the order was edited post-checkout) -- refuse to mark it paid.
    if payment.amount != order.total:
        payment.status = Payment.Status.FAILED
        payment.failure_reason = "Amount mismatch between payment and order."
        payment.save(update_fields=["status", "failure_reason", "updated_at"])
        _set_order_payment_status(order, Order.PaymentStatus.FAILED)
        logger.error(
            "Amount mismatch on payment %s: payment.amount=%s order.total=%s",
            payment.pk, payment.amount, order.total,
        )
        return payment

    payment.status = Payment.Status.SUCCESS
    payment.paid_at = timezone.now()
    payment.gateway_ref_id = gateway_ref_id
    payment.save(update_fields=["status", "paid_at", "gateway_ref_id", "updated_at"])

    order.payment_status = Order.PaymentStatus.PAID
    order.status = Order.Status.CONFIRMED
    order.save(update_fields=["payment_status", "status", "updated_at"])

    # Inventory transition -- see apps/orders/inventory.py for why this
    # is exactly-once and where oversell is handled.
    from apps.orders.inventory import decrement_stock_for_order

    decrement_stock_for_order(order)

    _record_coupon_usage(order)

    logger.info(
        "Payment %s verified: order %s paid (%s Toman).",
        payment.pk, order.order_number, payment.amount,
    )
    return payment


def _record_coupon_usage(order) -> None:
    """
    Records the order's coupon redemption NOW -- at payment success, not
    at checkout -- so abandoned unpaid orders never consume a coupon's
    usage quota. Defensive re-validation under a row lock on the coupon:
    if concurrent payments already exhausted the limits, we still keep
    the discount the customer was charged (the money already moved) but
    log the discrepancy loudly for reconciliation.
    """
    if not order.coupon_id:
        return

    from apps.discounts.models import Coupon, CouponUsage
    from apps.discounts.services import usage_within_limits

    with transaction.atomic():
        coupon = Coupon.objects.select_for_update().get(pk=order.coupon_id)
        if not usage_within_limits(coupon, order.user):
            logger.error(
                "Coupon %s exceeded its usage limits at payment time for order %s; "
                "honoring the charged discount but recording the discrepancy.",
                coupon.code, order.order_number,
            )
        CouponUsage.objects.create(coupon=coupon, user=order.user, order=order)


def _set_order_payment_status(order, status_value) -> None:
    order.payment_status = status_value
    order.save(update_fields=["payment_status", "updated_at"])
