"""
Notification delivery (Phase D - Notifications).

The ONE place notifications are composed and sent -- same single-
mechanism discipline as apps/orders/inventory.py or apps/orders/refunds.py.
Callers (payments services, orders workflow, accounts views) only say
WHICH event happened for WHICH object; everything else lives here:

    * Delivery is registered with transaction.on_commit, so nothing is
      sent for a transaction that later rolls back, and a slow or broken
      provider can never hold a database transaction open.
    * Failures NEVER propagate. A provider error, SMTP error, timeout or
      any unexpected exception is caught, logged, and recorded as a
      FAILED NotificationLog row -- checkout, payment verification and
      admin status changes cannot be broken by notifications.
    * Idempotency: for order events, the NotificationLog row is created
      BEFORE sending, and its partial unique constraint
      (event, order, channel) is the backstop -- replayed payment
      callbacks or repeated admin saves can never double-send.
    * Recipients are stored masked (mask_phone / mask_email); raw phone
      numbers and email addresses never enter the audit log.

Channels per event:
    order_confirmed / order_shipped   SMS (to the account phone) + email
                                      (to the account email, if any)
    password_reset                    email link (accounts with an email)
                                      OR SMS one-time code (phone-only
                                      accounts) -- chosen by the caller.
"""
import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from .messengers import get_enabled_messengers
from .models import NotificationLog
from .providers import get_provider

logger = logging.getLogger("notifications")


class Events:
    """The event vocabulary. Machine names stored in NotificationLog.event."""

    PASSWORD_RESET = "password_reset"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_SHIPPED = "order_shipped"
    # Part R4 item 3: OWNER-facing alerts (never sent to customers).
    OWNER_PAID_ORDER = "owner_paid_order"
    OWNER_LOW_STOCK = "owner_low_stock"


# ---------------------------------------------------------------------------
# Recipient masking (audit log never stores raw contact data)
# ---------------------------------------------------------------------------

def mask_phone(phone: str) -> str:
    """+989121234567 -> +989******567 ; 09121234567 -> 0912****567"""
    value = (phone or "").strip()
    if len(value) <= 4:
        return "*" * len(value)
    head = value[:4] if len(value) >= 8 else value[:2]
    tail = value[-3:]
    stars = "*" * max(len(value) - len(head) - len(tail), 3)
    return f"{head}{stars}{tail}"


def mask_email(email: str) -> str:
    """someone@example.com -> s***@example.com"""
    value = (email or "").strip()
    local, sep, domain = value.partition("@")
    if not sep or not domain:
        return "*" * min(len(value), 8) or "***"
    visible = local[:1]
    return f"{visible}***@{domain}"


# ---------------------------------------------------------------------------
# Order-event notifications
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _OrderNotice:
    """
    Immutable snapshot of everything delivery needs, captured INSIDE the
    caller's transaction. Delivery runs after commit and must not depend
    on ORM state (the in-memory order may be stale by then, and lazy
    loads after commit could hit deleted rows).
    """

    event: str
    order_id: int
    order_number: str
    total: int
    tracking_code: str
    shipping_method: str
    estimated_delivery_min: object
    estimated_delivery_max: object
    user_id: int
    phone: str
    email: str

    @classmethod
    def from_order(cls, order, event: str) -> "_OrderNotice":
        user = order.user
        return cls(
            event=event,
            order_id=order.pk,
            order_number=order.order_number,
            total=order.total,
            tracking_code=order.tracking_code or "",
            shipping_method=order.shipping_method,
            estimated_delivery_min=order.estimated_delivery_min,
            estimated_delivery_max=order.estimated_delivery_max,
            user_id=user.pk,
            # Notifications about an order go to the ACCOUNT holder, not
            # necessarily the shipping recipient (the parcel phone may be
            # somebody else's -- a gift, a family member).
            phone=user.phone or "",
            email=user.email or "",
        )


def notify_order_event(order, event: str) -> None:
    """
    Queue the customer notifications for one order event. Call from
    INSIDE the triggering transaction (payment completion, workflow
    status change); delivery happens on commit, failures are contained,
    and repeats of the same (event, order) never double-send.
    """
    notice = _OrderNotice.from_order(order, event)
    transaction.on_commit(lambda: _deliver_order_notice(notice))


def _deliver_order_notice(notice: _OrderNotice) -> None:
    """Post-commit delivery. NEVER raises -- see module docstring."""
    try:
        _deliver_order_sms(notice)
    except Exception:  # pragma: no cover - belt and braces; inner code already catches
        logger.exception("Unexpected error delivering SMS for %s", notice.order_number)
    try:
        _deliver_order_email(notice)
    except Exception:  # pragma: no cover
        logger.exception("Unexpected error delivering email for %s", notice.order_number)


def _deliver_order_sms(notice: _OrderNotice) -> None:
    if not settings.SMS_ENABLED:
        return  # deliberate opt-out (SMS_ENABLED=False); not an incident
    if not notice.phone:
        return  # account has no phone -- nothing to send to

    message, template, tokens = _order_sms_content(notice)
    log = _begin_log(
        event=notice.event, channel=NotificationLog.Channel.SMS,
        order_id=notice.order_id, user_id=notice.user_id,
        recipient_masked=mask_phone(notice.phone),
    )
    if log is None:
        return  # this (event, order, channel) was already handled

    try:
        message_id = get_provider().send(
            notice.phone, message=message, template=template, tokens=tokens
        )
        _finish_log(log, NotificationLog.Status.SENT, provider_message_id=message_id)
    except Exception as exc:
        _finish_log(log, NotificationLog.Status.FAILED, error=_error_text(exc))
        logger.error(
            "SMS send failed for %s (%s) to %s: %s",
            notice.order_number, notice.event, mask_phone(notice.phone), exc,
        )


def _deliver_order_email(notice: _OrderNotice) -> None:
    if not notice.email:
        return  # account has no email -- SMS-only customer, not an incident
    if _smtp_required_but_unconfigured():
        log = _begin_log(
            event=notice.event, channel=NotificationLog.Channel.EMAIL,
            order_id=notice.order_id, user_id=notice.user_id,
            recipient_masked=mask_email(notice.email),
        )
        if log is not None:
            _finish_log(log, NotificationLog.Status.SKIPPED,
                        error="EMAIL_HOST is not configured (SMTP disabled).")
        return

    subject, body = _order_email_content(notice)
    log = _begin_log(
        event=notice.event, channel=NotificationLog.Channel.EMAIL,
        order_id=notice.order_id, user_id=notice.user_id,
        recipient_masked=mask_email(notice.email),
    )
    if log is None:
        return

    try:
        send_mail(subject=subject, message=body, from_email=None,
                  recipient_list=[notice.email], fail_silently=False)
        _finish_log(log, NotificationLog.Status.SENT)
    except Exception as exc:
        _finish_log(log, NotificationLog.Status.FAILED, error=_error_text(exc))
        logger.error(
            "Email send failed for %s (%s) to %s: %s",
            notice.order_number, notice.event, mask_email(notice.email), exc,
        )


def _smtp_required_but_unconfigured() -> bool:
    """Email is 'optional through SMTP from env': with the SMTP backend
    selected but no EMAIL_HOST, sending cannot work -- record a SKIPPED
    row instead of failing every event. Console/locmem backends (dev and
    tests) always 'work'."""
    return "smtp" in settings.EMAIL_BACKEND.lower() and not (settings.EMAIL_HOST or "").strip()


# ---------------------------------------------------------------------------
# Password-reset notifications
# ---------------------------------------------------------------------------

def send_password_reset_email(user, reset_url: str) -> None:
    """The reset LINK email for accounts that have an email address.
    Not order-bound: every request is a distinct (rate-limited) event,
    so no idempotency constraint applies -- each gets its own log row."""
    snapshot = (user.pk, user.email, reset_url)
    transaction.on_commit(lambda: _deliver_password_reset_email(*snapshot))


def _deliver_password_reset_email(user_id: int, email: str, reset_url: str) -> None:
    if not email:
        return
    log = NotificationLog.objects.create(
        event=Events.PASSWORD_RESET, channel=NotificationLog.Channel.EMAIL,
        user_id=user_id, recipient_masked=mask_email(email),
    )
    try:
        if _smtp_required_but_unconfigured():
            _finish_log(log, NotificationLog.Status.SKIPPED,
                        error="EMAIL_HOST is not configured (SMTP disabled).")
            return
        # Subject/body kept byte-identical to the pre-Phase-D flow so the
        # link format the frontend expects (/reset-password/confirm/?uid=...)
        # and existing tests remain valid.
        send_mail(
            subject="Cusin Gallery - Password reset",
            message=(
                f"Use this link to reset your password: {reset_url}\n\n"
                "If you didn't request this, you can safely ignore this email."
            ),
            from_email=None,
            recipient_list=[email],
            fail_silently=False,
        )
        _finish_log(log, NotificationLog.Status.SENT)
    except Exception as exc:
        _finish_log(log, NotificationLog.Status.FAILED, error=_error_text(exc))
        logger.error("Password-reset email failed for user %s: %s", user_id, exc)


def send_password_reset_code(user, code: str) -> None:
    """The one-time reset CODE SMS for phone-only accounts. The code is
    generated/hashed/validated by apps.accounts (PhoneResetCode); this
    layer only delivers it."""
    snapshot = (user.pk, user.phone or "", code)
    transaction.on_commit(lambda: _deliver_password_reset_sms(*snapshot))


def _deliver_password_reset_sms(user_id: int, phone: str, code: str) -> None:
    if not phone:
        return
    log = NotificationLog.objects.create(
        event=Events.PASSWORD_RESET, channel=NotificationLog.Channel.SMS,
        user_id=user_id, recipient_masked=mask_phone(phone),
    )
    try:
        if not settings.SMS_ENABLED:
            _finish_log(log, NotificationLog.Status.SKIPPED,
                        error="SMS_ENABLED=False -- no SMS provider configured.")
            logger.warning(
                "Password reset requested for phone-only account (user %s) but SMS is "
                "disabled; nothing could be sent.", user_id,
            )
            return
        template = (settings.SMS_TEMPLATE_PASSWORD_RESET or "").strip()
        if template:
            message_id = get_provider().send(phone, template=template, tokens={"token": code})
        else:
            message = (
                f"کد بازیابی رمز عبور کازین گالری: {code}\n"
                f"اعتبار: {settings.PASSWORD_RESET_CODE_TTL_MINUTES} دقیقه. "
                "این کد را با کسی به اشتراک نگذارید."
            )
            message_id = get_provider().send(phone, message=message)
        _finish_log(log, NotificationLog.Status.SENT, provider_message_id=message_id)
    except Exception as exc:
        _finish_log(log, NotificationLog.Status.FAILED, error=_error_text(exc))
        logger.error("Password-reset SMS failed for user %s: %s", user_id, exc)


# ---------------------------------------------------------------------------
# Content (Persian customer-facing copy lives here, in exactly one place)
# ---------------------------------------------------------------------------

def _order_sms_content(notice: _OrderNotice):
    """(direct_message, template_name, template_tokens) for an order event.
    Template names come from env; when one is empty the provider falls
    back to the locally-composed direct message."""
    if notice.event == Events.ORDER_CONFIRMED:
        template = (settings.SMS_TEMPLATE_ORDER_CONFIRMED or "").strip()
        tokens = {"token": notice.order_number, "token2": f"{notice.total}"}
        message = (
            f"سفارش {notice.order_number} در کازین گالری با موفقیت پرداخت و ثبت شد. "
            f"مبلغ: {notice.total:,} تومان"
        )
    elif notice.event == Events.ORDER_SHIPPED and notice.shipping_method == "pickup":
        # Pickup orders have no carrier: "shipped" means READY FOR
        # PICKUP, and the message carries WHERE/WHEN instead of a
        # tracking code (Part 1). Template mode is deliberately skipped
        # here -- panel templates are built for courier tracking codes.
        from apps.core.models import SiteSettings

        site = SiteSettings.load()
        template = ""
        tokens = {}
        message = (
            f"سفارش {notice.order_number} کازین گالری آمادهٔ دریافت حضوری است. "
            f"نشانی: {site.pickup_address or '-'}"
            + (f" | ساعات دریافت: {site.pickup_hours}" if site.pickup_hours else "")
        )
    elif notice.event == Events.ORDER_SHIPPED:
        template = (settings.SMS_TEMPLATE_ORDER_SHIPPED or "").strip()
        tokens = {"token": notice.order_number, "token2": notice.tracking_code or "-"}
        message = (
            f"سفارش {notice.order_number} کازین گالری ارسال شد. "
            f"کد رهگیری پستی: {notice.tracking_code or '-'}"
        )
    else:  # pragma: no cover - guarded by callers
        raise ValueError(f"Unknown order event: {notice.event}")
    return message, template, tokens


def _order_email_content(notice: _OrderNotice):
    shipping_label = "اکسپرس" if notice.shipping_method == "express" else "استاندارد"
    if notice.event == Events.ORDER_CONFIRMED:
        subject = f"تأیید سفارش {notice.order_number} — کازین گالری"
        lines = [
            "سلام،",
            "",
            f"سفارش {notice.order_number} با موفقیت پرداخت و ثبت شد.",
            f"مبلغ کل: {notice.total:,} تومان",
            f"روش ارسال: {shipping_label}",
        ]
        if notice.estimated_delivery_min and notice.estimated_delivery_max:
            lines.append(
                "بازهٔ تحویل تخمینی: "
                f"{notice.estimated_delivery_min:%Y/%m/%d} تا {notice.estimated_delivery_max:%Y/%m/%d}"
            )
        lines += [
            "",
            "می‌توانید وضعیت سفارش را در حساب کاربری خود پیگیری کنید.",
            "با تشکر — کازین گالری (cusin.ir)",
        ]
    elif notice.event == Events.ORDER_SHIPPED and notice.shipping_method == "pickup":
        from apps.core.models import SiteSettings

        site = SiteSettings.load()
        subject = f"سفارش {notice.order_number} آمادهٔ دریافت حضوری — کازین گالری"
        lines = [
            "سلام،",
            "",
            f"سفارش {notice.order_number} آمادهٔ تحویل حضوری است.",
            f"نشانی دریافت: {site.pickup_address or '-'}",
        ]
        if site.pickup_hours:
            lines.append(f"ساعات دریافت: {site.pickup_hours}")
        lines += ["", "با تشکر — کازین گالری (cusin.ir)"]
    elif notice.event == Events.ORDER_SHIPPED:
        subject = f"سفارش {notice.order_number} ارسال شد — کازین گالری"
        lines = [
            "سلام،",
            "",
            f"سفارش {notice.order_number} ارسال شد.",
            f"کد رهگیری پستی: {notice.tracking_code or '-'}",
            f"روش ارسال: {shipping_label}",
            "",
            "با تشکر — کازین گالری (cusin.ir)",
        ]
    else:  # pragma: no cover
        raise ValueError(f"Unknown order event: {notice.event}")
    return subject, "\n".join(lines)


# ---------------------------------------------------------------------------
# NotificationLog plumbing
# ---------------------------------------------------------------------------

def _begin_log(event: str, channel: str, recipient_masked: str,
               order_id=None, user_id=None):
    """
    Create the PENDING audit row BEFORE sending. Returns None when the
    (event, order, channel) row already exists -- the database-level
    idempotency answer to "the same event must never be sent twice for
    the same order". The savepoint keeps the IntegrityError safe even
    when delivery somehow runs inside an outer atomic block (tests).
    """
    try:
        with transaction.atomic():
            return NotificationLog.objects.create(
                event=event, channel=channel, status=NotificationLog.Status.PENDING,
                order_id=order_id, user_id=user_id, recipient_masked=recipient_masked,
            )
    except IntegrityError:
        return None


def _finish_log(log: NotificationLog, status: str, error: str = "",
                provider_message_id: str = "") -> None:
    log.status = status
    log.error = error[:2000]
    log.provider_message_id = (provider_message_id or "")[:64]
    log.save(update_fields=["status", "error", "provider_message_id", "updated_at"])


def _error_text(exc: Exception) -> str:
    """Never let an exception's text leak secrets (provider errors are
    already written to avoid URLs/keys, this is the last line of defense)
    and keep the stored error bounded."""
    return f"{type(exc).__name__}: {exc}"[:2000]


# ---------------------------------------------------------------------------
# Owner alerts (Part R4 item 3)
# ---------------------------------------------------------------------------
# The shop owner is told about two things customers never trigger for
# themselves: a newly PAID order, and stock crossing down to/through the
# low-stock threshold after a sale. Recipients come ONLY from env
# (OWNER_ALERT_PHONES / OWNER_ALERT_EMAILS); an empty value turns that
# channel off. Messenger bots (Telegram/Bale, apps/notifications/
# messengers.py) join in only when explicitly configured. Everything runs
# post-commit, is idempotent per (event, order, channel) through the
# NotificationLog unique constraint, and NEVER raises into the payment or
# inventory flows.

def _split_csv(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _admin_order_url(order_id):
    """Deep link into the order's admin change page, honouring the
    configurable ADMIN_URL path (Part R3)."""
    import os

    admin_path = (os.environ.get("ADMIN_URL", "admin/") or "admin/").strip().strip("/") or "admin"
    return f"{settings.FRONTEND_URL.rstrip('/')}/{admin_path}/orders/order/{order_id}/change/"


@dataclass(frozen=True)
class _OwnerOrderNotice:
    """Post-commit snapshot of a newly paid order for the owner alert."""

    order_id: int
    order_number: str
    total: int
    item_count: int
    shipping_label: str
    customer_name: str
    customer_phone: str
    admin_url: str


def notify_owner_new_paid_order(order) -> None:
    """Queue the owner alert for a newly paid order. Call INSIDE the
    payment-verification transaction (delivery is on_commit)."""
    from apps.orders.shipping import method_label

    user = order.user
    notice = _OwnerOrderNotice(
        order_id=order.pk,
        order_number=order.order_number,
        total=order.total,
        item_count=sum(item.quantity for item in order.items.all()),
        shipping_label=method_label(order.shipping_method),
        customer_name=(user.get_full_name() or "").strip() or "-",
        customer_phone=user.phone or "",
        admin_url=_admin_order_url(order.pk),
    )
    transaction.on_commit(lambda: _deliver_owner_paid_order(notice))


def _owner_paid_order_text(notice: _OwnerOrderNotice) -> str:
    return (
        "سفارش جدید پرداخت شد - کازین گالری\n"
        f"شماره سفارش: {notice.order_number}\n"
        f"مبلغ: {notice.total:,} تومان\n"
        f"تعداد اقلام: {notice.item_count}\n"
        f"روش ارسال: {notice.shipping_label}\n"
        f"مشتری: {notice.customer_name} ({notice.customer_phone})\n"
        f"پنل مدیریت: {notice.admin_url}"
    )


def _deliver_owner_paid_order(notice: _OwnerOrderNotice) -> None:
    """Post-commit owner delivery. NEVER raises."""
    try:
        text = _owner_paid_order_text(notice)
        _deliver_owner_alert(
            event=Events.OWNER_PAID_ORDER,
            order_id=notice.order_id,
            sms_text=text,
            email_subject=f"سفارش جدید پرداخت شد: {notice.order_number}",
            email_body=text,
        )
    except Exception:  # pragma: no cover - containment backstop
        logger.exception("Unexpected error delivering owner paid-order alert %s",
                         notice.order_number)


def notify_owner_low_stock(order, crossings) -> None:
    """Queue ONE owner alert for every stock crossing detected by this
    order's decrement. `crossings` is a list of (label, remaining) tuples
    captured while the row locks are held; delivery is on_commit."""
    if not crossings:
        return
    snapshot = (order.pk, order.order_number, tuple(crossings))
    transaction.on_commit(lambda: _deliver_owner_low_stock(*snapshot))


def _owner_low_stock_text(order_number, crossings) -> str:
    lines = ["هشدار موجودی کم - کازین گالری"]
    for label, remaining in crossings:
        lines.append(f"- {label}: موجودی {remaining}")
    lines.append(f"سفارش مربوط: {order_number}")
    lines.append(f"آستانه هشدار: {settings.LOW_STOCK_THRESHOLD}")
    return "\n".join(lines)


def _deliver_owner_low_stock(order_id, order_number, crossings) -> None:
    try:
        text = _owner_low_stock_text(order_number, crossings)
        _deliver_owner_alert(
            event=Events.OWNER_LOW_STOCK,
            order_id=order_id,
            sms_text=text,
            email_subject="هشدار موجودی کم - کازین گالری",
            email_body=text,
        )
    except Exception:  # pragma: no cover
        logger.exception("Unexpected error delivering owner low-stock alert")


def _deliver_owner_alert(event, order_id, sms_text, email_subject, email_body) -> None:
    """The shared per-channel delivery for owner alerts. Each channel gets
    ONE NotificationLog row (the idempotency backstop); inside a channel,
    every configured recipient is attempted and one recipient's failure
    never stops the others."""
    phones = _split_csv(settings.OWNER_ALERT_PHONES)
    emails = _split_csv(settings.OWNER_ALERT_EMAILS)

    if phones:
        log = _begin_log(
            event=event, channel=NotificationLog.Channel.SMS, order_id=order_id,
            recipient_masked="، ".join(mask_phone(p) for p in phones),
        )
        if log is not None:
            try:
                if not settings.SMS_ENABLED:
                    _finish_log(log, NotificationLog.Status.SKIPPED,
                                error="SMS_ENABLED=False -- owner SMS channel off.")
                else:
                    sent_ids, errors = [], []
                    for phone in phones:
                        try:
                            sent_ids.append(get_provider().send(phone, message=sms_text))
                        except Exception as exc:
                            errors.append(f"{mask_phone(phone)}: {_error_text(exc)}")
                            logger.error("Owner SMS failed (%s): %s", mask_phone(phone), exc)
                    if sent_ids:
                        _finish_log(log, NotificationLog.Status.SENT,
                                    error="; ".join(errors),
                                    provider_message_id=sent_ids[0])
                    else:
                        _finish_log(log, NotificationLog.Status.FAILED,
                                    error="; ".join(errors) or "no recipients")
            except Exception as exc:
                _finish_log(log, NotificationLog.Status.FAILED, error=_error_text(exc))

    if emails:
        log = _begin_log(
            event=event, channel=NotificationLog.Channel.EMAIL, order_id=order_id,
            recipient_masked="، ".join(mask_email(e) for e in emails),
        )
        if log is not None:
            try:
                if _smtp_required_but_unconfigured():
                    _finish_log(log, NotificationLog.Status.SKIPPED,
                                error="EMAIL_HOST is not configured (SMTP disabled).")
                else:
                    send_mail(subject=email_subject, message=email_body, from_email=None,
                              recipient_list=emails, fail_silently=False)
                    _finish_log(log, NotificationLog.Status.SENT)
            except Exception as exc:
                _finish_log(log, NotificationLog.Status.FAILED, error=_error_text(exc))
                logger.error("Owner email failed for %s: %s", event, exc)

    messengers = get_enabled_messengers()
    if messengers:
        log = _begin_log(
            event=event, channel=NotificationLog.Channel.MESSENGER, order_id=order_id,
            recipient_masked="، ".join(f"{m.name}:{mask_phone(str(m.chat_id))}"
                                       for m in messengers),
        )
        if log is not None:
            sent_ids, errors = [], []
            for messenger in messengers:
                try:
                    sent_ids.append(messenger.send(sms_text))
                except Exception as exc:
                    errors.append(f"{messenger.name}: {_error_text(exc)}")
                    logger.error("Owner messenger (%s) failed: %s", messenger.name, exc)
            if sent_ids:
                _finish_log(log, NotificationLog.Status.SENT,
                            error="; ".join(errors),
                            provider_message_id=(sent_ids[0] or "")[:64])
            else:
                _finish_log(log, NotificationLog.Status.FAILED,
                            error="; ".join(errors) or "no messengers")
