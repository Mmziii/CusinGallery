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

There is deliberately NO transition when the gateway cannot be REACHED
during verification (GatewayError from gateway.verify): the money state
is genuinely unknown -- the customer may well have paid -- so the attempt
stays PENDING and the customer lands on the result page's "در حال
بررسی" state. A replayed callback later (ZarinPal answers a repeat
verify of a captured payment with its documented code 101) can still
complete it; nothing is ever marked FAILED just because OUR network
call failed, and nothing is marked SUCCESS without the gateway's own
verified answer.

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

#: Query-string keys that may carry the gateway's own transaction
#: reference, in priority order. ZarinPal sends "Authority" (PascalCase,
#: per its docs), the mock gateway sends "authority"; "token"/"Token"
#: are pre-registered for gateways like NextPay/IDPay so adding one
#: never requires touching this security-critical function's callers.
#: Whatever the key, the value is used ONLY to look the attempt up --
#: every decision still comes from gateway.verify().
GATEWAY_REFERENCE_KEYS = ("authority", "Authority", "token", "Token")


def _extract_gateway_reference(callback_data: dict) -> str:
    """First non-empty gateway transaction reference in the raw callback
    parameters (see GATEWAY_REFERENCE_KEYS), flattened and stripped."""
    for key in GATEWAY_REFERENCE_KEYS:
        raw = callback_data.get(key)
        if isinstance(raw, (list, tuple)):  # tolerate ?authority=a&authority=b
            raw = raw[0] if raw else ""
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return ""


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
    gateway_transaction_id = _extract_gateway_reference(callback_data)
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
    try:
        verification = gateway.verify(payment, callback_data)
    except GatewayError as exc:
        # The gateway could not be REACHED (timeout, DNS, HTTP 5xx,
        # malformed answer) while verifying. The money state is genuinely
        # unknown -- the customer may have paid at the gateway page --
        # so the attempt deliberately stays PENDING: marking it FAILED
        # could hide a real capture, and marking it SUCCESS would trust
        # nothing. The customer sees the result page's "pending" state;
        # a replayed callback (the customer refreshing, the gateway
        # re-notifying, or a retry) can still complete verification,
        # which ZarinPal explicitly supports via its code-101 answer.
        logger.error(
            "Gateway verification could not complete for payment %s: %s -- "
            "leaving the attempt PENDING.",
            payment.pk, exc,
        )
        return payment

    with transaction.atomic():
        # Re-read under the lock: another callback may have completed the
        # transition between our fast-path check and here.
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.status != Payment.Status.PENDING:
            return locked

        # Lock the ORDER row too, for every outcome: two DIFFERENT
        # attempts for the same order (both started while it was unpaid,
        # both now verifying) hold different payment-row locks and would
        # otherwise race -- toward the unique-success constraint on two
        # successes, or toward clobbering each other's order-status
        # writes on success-vs-cancel. Serializing on the order row makes
        # the later callback see the earlier one's result and behave;
        # the unique constraint remains only the final database-level
        # backstop. Lock order is always payment -> order -> catalog
        # rows (matching the stock decrement below), so no deadlock
        # cycles.
        order = Order.objects.select_for_update().get(pk=locked.order_id)
        locked.order = order

        if verification.success:
            # The gateway has confirmed REAL money was captured for this
            # attempt. What happens next depends on whether the order can
            # still receive it. `prior_success` is checked explicitly (not
            # only via order.payment_status) because a terminal order may
            # already carry its one allowed SUCCESS payment -- see the
            # unique_successful_payment_per_order constraint.
            prior_success = (
                Payment.objects.filter(order=order, status=Payment.Status.SUCCESS)
                .exclude(pk=locked.pk)
                .exists()
            )

            if not prior_success and order.status in (
                Order.Status.CANCELLED, Order.Status.RETURNED
            ):
                # Verified capture for an order that will NOT be fulfilled
                # (typically: the customer finished paying at the exact
                # moment `expire_unpaid_orders` auto-cancelled the stale
                # order). The money is real and must stay visible.
                return _record_capture_on_unfulfillable_order(locked, order, verification)

            if prior_success or order.payment_status == Order.PaymentStatus.PAID:
                logger.info(
                    "Rejecting late success callback for payment %s: order %s "
                    "already paid by another attempt.",
                    locked.pk, order.order_number,
                )
                locked.status = Payment.Status.FAILED
                locked.failure_reason = "Order already paid via another payment attempt."
                locked.save(update_fields=["status", "failure_reason", "updated_at"])
                # The customer was charged TWICE (both attempts verified)
                # -- the duplicate is real money owed back; flag it.
                _flag_duplicate_capture(order, locked)
                return locked
            try:
                # Savepoint: if the unique-success constraint fires
                # anyway (exotic race), roll back only the completion,
                # never crash the callback with a 500.
                with transaction.atomic():
                    return _complete_successful_payment(locked, verification)
            except IntegrityError:
                logger.error(
                    "unique_successful_payment_per_order fired for payment %s "
                    "(order %s) -- another attempt won; marking this attempt "
                    "FAILED without touching the already-paid order.",
                    locked.pk, order.order_number,
                )
                locked.status = Payment.Status.FAILED
                locked.failure_reason = "Order already paid via another payment attempt."
                locked.save(update_fields=["status", "failure_reason", "updated_at"])
                # Same duplicate-capture money story as the branch above.
                _flag_duplicate_capture(order, locked)
                return locked

        if verification.cancelled:
            locked.status = Payment.Status.CANCELLED
            locked.failure_reason = verification.failure_reason[:255]
            locked.save(update_fields=["status", "failure_reason", "updated_at"])
            # The order simply goes back to payable -- nothing happened.
            # Only if THIS attempt still owns the in-flight state: a
            # late-arriving cancel for an attempt whose order another
            # attempt already paid (or already reset) must not overwrite
            # that result.
            if order.payment_status == Order.PaymentStatus.PENDING:
                _set_order_payment_status(order, Order.PaymentStatus.UNPAID)
            return locked

        locked.status = Payment.Status.FAILED
        locked.failure_reason = verification.failure_reason[:255]
        locked.save(update_fields=["status", "failure_reason", "updated_at"])
        if order.payment_status == Order.PaymentStatus.PENDING:
            _set_order_payment_status(order, Order.PaymentStatus.FAILED)
        return locked


def _complete_successful_payment(payment: Payment, verification) -> Payment:
    """
    The single code path in which an order becomes paid. Everything that
    must happen exactly once per paid order lives inside the caller's
    atomic block, under the caller's row lock:

        payment  PENDING -> SUCCESS (+ ref id, card receipt data, paid_at)
        order    payment_status -> PAID, status -> CONFIRMED
        stock    decremented via apps.orders.inventory
        coupon   usage recorded (if the order used one)

    `verification` is the gateway's VerificationResult; beyond the
    boolean outcome it carries the PSP's receipt data (reference id,
    masked card PAN, card fingerprint), all of which come FROM THE
    GATEWAY'S OWN VERIFY ANSWER -- never from the callback query string.

    The partial unique constraint on successful payments is the final
    guard: if some exotic race ever got two attempts here for one order,
    the second insert/update raises IntegrityError and the whole
    transaction rolls back rather than double-paying.
    """
    order = payment.order

    # Amount integrity: the payment was initiated for order.total; if the
    # order row no longer matches that snapshot, something is very wrong
    # (the order was edited post-checkout) -- refuse to mark it paid.
    # This is the SECOND amount check: the gateway's verify call itself
    # also sent payment.amount (the amount the customer was actually
    # charged), so the PSP has already confirmed the money matches the
    # snapshot; this compares the snapshot against the order.
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
    payment.gateway_ref_id = verification.gateway_ref_id[:128]
    payment.card_pan = verification.card_pan[:32]
    payment.card_pan_hash = verification.card_fingerprint[:64]
    payment.save(
        update_fields=[
            "status", "paid_at", "gateway_ref_id",
            "card_pan", "card_pan_hash", "updated_at",
        ]
    )

    order.payment_status = Order.PaymentStatus.PAID
    order.status = Order.Status.CONFIRMED
    order.save(update_fields=["payment_status", "status", "updated_at"])

    # Inventory transition -- see apps/orders/inventory.py for why this
    # is exactly-once and where oversell is handled.
    from apps.orders.inventory import decrement_stock_for_order

    decrement_stock_for_order(order)

    _record_coupon_usage(order)

    # Customer notification (Phase D): order confirmation over SMS and/or
    # email. Registered via transaction.on_commit inside apps/notifications
    # -- nothing is sent unless this whole transition actually commits,
    # the delivery never holds this transaction open, provider failures
    # can never break the payment, and the NotificationLog unique
    # constraint keeps replayed callbacks from notifying twice.
    from apps.notifications.services import (
        Events,
        notify_order_event,
        notify_owner_new_paid_order,
    )

    notify_order_event(order, Events.ORDER_CONFIRMED)
    # Part R4 item 3: tell the OWNER a paid order arrived (on_commit,
    # idempotent, provider failures can never break this transition).
    notify_owner_new_paid_order(order)

    logger.info(
        "Payment %s verified: order %s paid (%s Toman).",
        payment.pk, order.order_number, payment.amount,
    )
    return payment


def _record_capture_on_unfulfillable_order(payment: Payment, order, verification) -> Payment:
    """
    The gateway VERIFIED a real capture, but the order is already in a
    terminal status (cancelled/returned) and will not be fulfilled --
    typically the customer completed payment at the exact moment the
    `expire_unpaid_orders` cron cancelled the stale order.

    The money moved, so the payment record tells the truth: SUCCESS with
    the full receipt data (ref id, masked PAN, fingerprint). The ORDER is
    not fulfilled: no status change (it can't leave a terminal status),
    NO stock decrement (nothing ships) and no coupon usage. It shows
    payment_status=PAID -- the customer genuinely paid -- and is flagged
    REFUND REQUIRED so the captured amount appears in the owner's refund
    queue instead of vanishing. See apps/orders/workflow.py's docstring
    for why this is the one documented exception to the
    "PAID == stock decremented" equivalence (restore can never fire:
    the order is already terminal).

    Runs inside handle_callback's locked transaction (payment and order
    rows are already select_for_update-locked by the caller).
    """
    payment.status = Payment.Status.SUCCESS
    payment.paid_at = timezone.now()
    payment.gateway_ref_id = verification.gateway_ref_id[:128]
    payment.card_pan = verification.card_pan[:32]
    payment.card_pan_hash = verification.card_fingerprint[:64]
    payment.save(update_fields=[
        "status", "paid_at", "gateway_ref_id", "card_pan", "card_pan_hash", "updated_at",
    ])

    order.payment_status = Order.PaymentStatus.PAID
    order.save(update_fields=["payment_status", "updated_at"])

    from apps.orders.refunds import flag_refund_required

    flag_refund_required(
        order,
        amount=payment.amount,
        note="پرداخت پس از لغو/مرجوعی سفارش توسط درگاه تأیید شد — مبلغ دریافتی باید به مشتری بازگردانده شود.",
    )
    logger.error(
        "Payment %s verified (%s Toman) but order %s is already '%s' -- capture "
        "recorded, order flagged REFUND REQUIRED, nothing fulfilled.",
        payment.pk, payment.amount, order.order_number, order.status,
    )
    return payment


def _flag_duplicate_capture(order, payment: Payment) -> None:
    """
    A second gateway-verified capture on one order (the customer paid two
    attempts -- e.g. two open browser tabs). The first capture paid the
    order; this one is real money the shop owes back. The payment row is
    FAILED (the unique-success constraint allows exactly one SUCCESS per
    order), but the money is never invisible: the order's refund ledger
    accumulates the amount and the journal records which transaction to
    refund, surfacing it in the owner's "needs refund" admin filter.
    """
    from apps.orders.refunds import flag_refund_required

    flag_refund_required(
        order,
        amount=payment.amount,
        note=(
            f"پرداخت تکراری تأییدشده (تراکنش #{payment.pk}) برای سفارشی که پیش‌تر "
            f"پرداخت شده بود — این مبلغ باید به مشتری بازگردانده شود."
        ),
    )


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
