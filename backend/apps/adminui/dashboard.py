"""Admin dashboard payload (B1) -- read-only aggregates for admin/index.

Design rules kept from the spec:
* aggregate/conditional-aggregate queries only -- no N+1, bounded total
  query count (asserted in tests);
* whole payload is plain data (dicts/ints/datetimes) cached ~60s so a
  refresh costs zero queries;
* Asia/Tehran day boundaries (the owner's notion of "today");
* per-model permission gating happens at render time from the same
  payload; the linked URLs are stock admin changelists which already
  enforce permissions.

Metric definitions (also documented in docs/OWNER_GUIDE.fa.md):
* gross sales (فروش ناخالص) = sum of ``Order.total`` for orders CREATED in
  the period whose ``payment_status == paid``;
* cancelled/returned money = the part of gross whose order ``status`` is
  cancelled or returned; shown separately, excluded from NET sales;
* net sales = gross - cancelled/returned;
* AOV (میانگین سبد) = gross / count of paid orders in the period;
* new customers = non-staff ``User.date_joined`` in the period;
* percent change compares against the immediately preceding period of the
  same length (yesterday / previous 7d / previous 30d).
"""
from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.admin.models import DELETION, LogEntry
from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.discounts.models import Coupon
from apps.notifications.models import NotificationLog
from apps.orders.models import Order
from apps.products.models import BackInStockSubscription, Product
from apps.reviews.models import Review

TEHRAN = ZoneInfo("Asia/Tehran")

CACHE_SECONDS = 60
CACHE_KEY = "adminui:dashboard:v2:{days}"

PAID_Q = Q(payment_status=Order.PaymentStatus.PAID)
CANCELLED_RETURNED_Q = Q(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])
# money that counts as a real sale: paid and not cancelled/returned
NET_Q = PAID_Q & ~CANCELLED_RETURNED_Q
# orders still waiting for fulfilment
OPEN_STATUSES = [
    Order.Status.PENDING, Order.Status.CONFIRMED,
    Order.Status.PROCESSING, Order.Status.SHIPPED,
]


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------

def _tehran_today() -> dt.date:
    return timezone.localtime(timezone.now(), TEHRAN).date()


def _utc_midnight(day: dt.date) -> dt.datetime:
    """Start of a Tehran calendar day as an aware UTC datetime."""
    return dt.datetime.combine(day, dt.time.min, tzinfo=TEHRAN).astimezone(dt.timezone.utc)


def _period(days: int) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    """(current_start, prev_start, exclusive_end) for a rolling ``days``
    window ending at the end of today (Tehran)."""
    today = _tehran_today()
    end = _utc_midnight(today + dt.timedelta(days=1))
    start = _utc_midnight(today - dt.timedelta(days=days - 1))
    prev_start = _utc_midnight(today - dt.timedelta(days=2 * days - 1))
    return start, prev_start, end


def _pct_change(current: float | int, previous: float | int) -> float | None:
    if not previous:
        return None
    return (float(current) - float(previous)) / float(previous) * 100.0


# ---------------------------------------------------------------------------
# KPI blocks
# ---------------------------------------------------------------------------

def _kpi_block(start: dt.datetime, prev_start: dt.datetime, end: dt.datetime) -> dict:
    """One Order query + one User query covering current AND previous period
    (conditional aggregation), so each KPI block costs exactly 2 queries."""
    o = Order.objects.filter(created_at__gte=prev_start, created_at__lt=end).aggregate(
        cur_orders=Count("pk", filter=Q(created_at__gte=start)),
        prev_orders=Count("pk", filter=Q(created_at__lt=start)),
        cur_gross=Sum("total", filter=Q(created_at__gte=start) & PAID_Q),
        prev_gross=Sum("total", filter=Q(created_at__lt=start) & PAID_Q),
        cur_paid=Count("pk", filter=Q(created_at__gte=start) & PAID_Q),
        prev_paid=Count("pk", filter=Q(created_at__lt=start) & PAID_Q),
        cur_cancelled=Sum(
            "total", filter=Q(created_at__gte=start) & PAID_Q & CANCELLED_RETURNED_Q,
        ),
        prev_cancelled=Sum(
            "total", filter=Q(created_at__lt=start) & PAID_Q & CANCELLED_RETURNED_Q,
        ),
    )
    u = User.objects.filter(
        date_joined__gte=prev_start, date_joined__lt=end, is_staff=False,
    ).aggregate(
        cur_customers=Count("pk", filter=Q(date_joined__gte=start)),
        prev_customers=Count("pk", filter=Q(date_joined__lt=start)),
    )

    def block(prefix: str, agg: dict) -> dict:
        gross = agg[f"{prefix}_gross"] or 0
        cancelled = agg[f"{prefix}_cancelled"] or 0
        paid = agg[f"{prefix}_paid"] or 0
        return {
            "orders": agg[f"{prefix}_orders"],
            "gross": gross,
            "cancelled_returned": cancelled,
            "net": gross - cancelled,
            "aov": round(gross / paid) if paid else 0,
        }

    cur, prev = block("cur", o), block("prev", o)
    cur["new_customers"] = u["cur_customers"]
    prev["new_customers"] = u["prev_customers"]

    changes = {
        key: _pct_change(cur[key], prev[key])
        for key in ("orders", "gross", "aov", "new_customers")
    }
    return {"current": cur, "previous": prev, "changes": changes}


# ---------------------------------------------------------------------------
# "needs action" cards
# ---------------------------------------------------------------------------

def _changelist(app: str, model: str) -> str:
    try:
        return reverse(f"admin:{app}_{model}_changelist")
    except NoReverseMatch:  # pragma: no cover - defensive
        return "/admin/"


def _action_cards(today: dt.date) -> list[dict]:
    """Counts + links for the «نیاز به اقدام» row.

    Each card carries the perm codename the template checks before
    rendering it; the target URL is a stock changelist (already
    permission-protected). Counts come from 6 conditional-aggregate
    queries total -- one per model family.
    """
    threshold = settings.LOW_STOCK_THRESHOLD

    o = Order.objects.aggregate(
        paid_to_process=Count(
            "pk",
            filter=PAID_Q & Q(status__in=[
                Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PROCESSING,
            ]),
        ),
        awaiting_payment=Count(
            "pk",
            filter=Q(payment_status__in=[
                Order.PaymentStatus.UNPAID, Order.PaymentStatus.PENDING,
            ]) & Q(status__in=OPEN_STATUSES),
        ),
        needs_refund=Count(
            "pk", filter=Q(refund_status=Order.RefundStatus.REQUIRED),
        ),
        pickup_waiting=Count(
            "pk",
            filter=PAID_Q & Q(shipping_method="pickup") & Q(
                status__in=[
                    Order.Status.PENDING, Order.Status.CONFIRMED,
                    Order.Status.PROCESSING, Order.Status.SHIPPED,
                ],
            ),
        ),
    )
    p = Product.objects.aggregate(
        low_stock=Count(
            "pk", filter=Q(stock_quantity__lte=threshold, stock_quantity__gt=0),
        ),
        out_of_stock=Count("pk", filter=Q(stock_quantity=0)),
        no_image=Count("pk", filter=Q(images__isnull=True), distinct=True),
    )
    reviews_pending = Review.objects.filter(status=Review.Status.PENDING).count()
    restocks = BackInStockSubscription.objects.filter(notified_at__isnull=True).count()
    week_ago = timezone.now() - dt.timedelta(days=7)
    failed_sms = NotificationLog.objects.filter(
        status=NotificationLog.Status.FAILED, created_at__gte=week_ago,
    ).count()
    expiring = Coupon.objects.filter(
        is_active=True,
        expiration_date__isnull=False,
        expiration_date__gte=_utc_midnight(today),
        expiration_date__lt=_utc_midnight(today + dt.timedelta(days=7)),
    ).count()

    orders_url = _changelist("orders", "order")
    products_url = _changelist("products", "product")
    exp_date = today.isoformat()
    exp_limit = (today + dt.timedelta(days=7)).isoformat()
    return [
        {
            "id": "paid_to_process", "count": o["paid_to_process"],
            "label": "پرداخت‌شده در انتظار پردازش",
            "hint": "سفارش‌های پرداخت‌شده‌ای که هنوز ارسال نشده‌اند.",
            "icon": "truck", "perm": "orders.view_order",
            "url": f"{orders_url}?queue=paid_to_process",
        },
        {
            "id": "awaiting_payment", "count": o["awaiting_payment"],
            "label": "در انتظار پرداخت",
            "hint": "سفارش‌های باز با وضعیت پرداخت نشده/در انتظار.",
            "icon": "hourglass", "perm": "orders.view_order",
            "url": f"{orders_url}?queue=awaiting_payment",
        },
        {
            "id": "needs_refund", "count": o["needs_refund"],
            "label": "نیازمند بازپرداخت وجه",
            "hint": "سفارش‌های لغو/مرجوع شده‌ای که پولشان برگشت داده نشده.",
            "icon": "refund", "perm": "orders.view_order",
            "url": f"{orders_url}?refund_status__exact=required",
        },
        {
            "id": "pickup_waiting", "count": o["pickup_waiting"],
            "label": "حضوری تحویل‌نشده",
            "hint": "سفارش‌های پرداخت‌شدهٔ حضوری که هنوز تحویل نشده‌اند.",
            "icon": "store", "perm": "orders.view_order",
            "url": f"{orders_url}?queue=pickup_waiting",
        },
        {
            "id": "low_stock", "count": p["low_stock"],
            "label": "موجودی کم",
            "hint": f"کالاهای دارای موجودی ≤ {threshold} (و بیشتر از صفر).",
            "icon": "alert-triangle", "perm": "products.view_product",
            # value "3" = at/below threshold but NOT zero, so the list the
            # owner opens shows exactly the rows the card counted.
            "url": f"{products_url}?low_stock=3",
        },
        {
            "id": "out_of_stock", "count": p["out_of_stock"],
            "label": "ناموجود",
            "hint": "کالاهایی با موجودی صفر.",
            "icon": "package-x", "perm": "products.view_product",
            "url": f"{products_url}?low_stock=2",
        },
        {
            "id": "no_image", "count": p["no_image"],
            "label": "بدون تصویر",
            "hint": "کالاهایی که هیچ تصویری ندارند.",
            "icon": "image-off", "perm": "products.view_product",
            "url": f"{products_url}?has_image=0",
        },
        {
            "id": "pending_reviews", "count": reviews_pending,
            "label": "نظر در انتظار تأیید",
            "hint": "نظراتی که هنوز بررسی نشده‌اند.",
            "icon": "star", "perm": "reviews.view_review",
            "url": f"{_changelist('reviews', 'review')}?status__exact=pending",
        },
        {
            "id": "restock_unnotified", "count": restocks,
            "label": "اطلاعیهٔ موجودی ارسال‌نشده",
            "hint": "مشترکان «خبرم کن» که هنوز پیامک نگرفته‌اند.",
            "icon": "bell-ring", "perm": "products.view_backinstocksubscription",
            "url": (
                f"{_changelist('products', 'backinstocksubscription')}"
                "?notified_at__isnull=1"
            ),
        },
        {
            "id": "failed_sms", "count": failed_sms,
            "label": "پیامک ناموفق (۷ روز)",
            "hint": "اعلان‌هایی که در ۷ روز گذشته ارسالشان شکست خورد.",
            "icon": "mail-x", "perm": "notifications.view_notificationlog",
            "url": (
                f"{_changelist('notifications', 'notificationlog')}"
                f"?status__exact=failed&created_at__gte={(today - dt.timedelta(days=7)).isoformat()}"
            ),
        },
        {
            "id": "expiring_coupons", "count": expiring,
            "label": "کوپن در حال انقضا (۷ روز)",
            "hint": "کوپن‌های فعالی که تا ۷ روز دیگر منقضی می‌شوند.",
            "icon": "ticket-clock", "perm": "discounts.view_coupon",
            "url": (
                f"{_changelist('discounts', 'coupon')}"
                f"?is_active__exact=1&expiration_date__gte={exp_date}&expiration_date__lt={exp_limit}"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# chart + lists
# ---------------------------------------------------------------------------

def _chart(days: int) -> list[dict]:
    """Daily gross sales for the last ``days`` Tehran days (1 query)."""
    from apps.adminui.jalali import fa_digits, format_jalali, to_jalali

    start = _utc_midnight(_tehran_today() - dt.timedelta(days=days - 1))
    rows = (
        Order.objects.filter(created_at__gte=start)
        .annotate(day=TruncDate("created_at", tzinfo=TEHRAN))
        .values("day")
        .annotate(gross=Sum("total", filter=PAID_Q), orders=Count("pk", filter=PAID_Q))
        .order_by("day")
    )
    by_day = {row["day"]: row for row in rows if row["day"]}
    today = _tehran_today()
    points = []
    for offset in range(days - 1, -1, -1):
        day = today - dt.timedelta(days=offset)
        row = by_day.get(day)
        jd = to_jalali(day)
        points.append({
            "date": day,
            # Short Jalali axis label: «۰۷/۱۸»
            "jlabel": fa_digits(f"{jd.jalali_month:02d}/{jd.jalali_day:02d}"),
            "jfull": format_jalali(day),
            "gross": (row["gross"] or 0) if row else 0,
            "orders": row["orders"] if row else 0,
        })
    return points


def _top_products(days: int, limit: int = 5) -> list[dict]:
    """Top products by sold quantity among paid, non-cancelled orders (1 query)."""
    start = _utc_midnight(_tehran_today() - dt.timedelta(days=days - 1))
    rows = (
        Order.objects.filter(created_at__gte=start)
        .filter(NET_Q)
        .values("items__product_id", "items__product_name")
        .annotate(qty=Sum("items__quantity"))
        .order_by("-qty")[:limit]
    )
    out = []
    for row in rows:
        pid = row["items__product_id"]
        out.append({
            "product_id": pid,
            "name": row["items__product_name"] or "—",
            "qty": row["qty"] or 0,
            "url": (
                reverse("admin:products_product_change", args=[pid])
                if pid else ""
            ),
        })
    return out


def _choice_label(choices_enum, value: str) -> str:
    for raw, label in choices_enum.choices:
        if raw == value:
            return label
    return value or ""


def _latest_orders(limit: int = 10) -> list[dict]:
    rows = (
        Order.objects.select_related("user")
        .order_by("-created_at")
        .values(
            "id", "order_number", "status", "payment_status", "total",
            "created_at", "user__first_name", "user__last_name", "user__username",
        )[:limit]
    )
    out = []
    for row in rows:
        row["status_label"] = _choice_label(Order.Status, row["status"])
        row["payment_label"] = _choice_label(Order.PaymentStatus, row["payment_status"])
        row["url"] = reverse("admin:orders_order_change", args=[row["id"]])
        out.append(row)
    return out


LOG_ACTION_LABELS = {1: "افزودن", 2: "ویرایش", 3: "حذف"}


def _latest_logs(limit: int = 10) -> list[dict]:
    rows = (
        LogEntry.objects.select_related("user", "content_type")
        .order_by("-action_time")
        .values(
            "id", "action_time", "user__first_name", "user__last_name",
            "user__username", "object_repr", "change_message", "action_flag",
            "content_type__app_label", "content_type__model", "object_id",
        )[:limit]
    )
    out = []
    for row in rows:
        row["action_label"] = LOG_ACTION_LABELS.get(row["action_flag"], "")
        row["url"] = ""
        if row["action_flag"] != DELETION and row["content_type__model"]:
            try:
                row["url"] = reverse(
                    f"admin:{row['content_type__app_label']}_{row['content_type__model']}_change",
                    args=[row["object_id"]],
                )
            except NoReverseMatch:
                row["url"] = ""
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# launch readiness (superuser card)
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def readiness_checks() -> list[dict]:
    """Reuses the same environment reads as ``manage.py check_production``
    (see apps/core/management/commands/check_production.py) so the card and
    the command never disagree. ``ok=True`` means launch-ready."""
    gateway = (settings.PAYMENT_GATEWAY or "").strip().lower()
    if not gateway or gateway == "mock":
        gw_ok, gw_detail = False, "درگاه پرداخت روی حالت آزمایشی (mock) است."
    elif gateway == "zarinpal" and settings.PAYMENT_ZARINPAL_SANDBOX:
        gw_ok, gw_detail = False, "زرین‌پال در حالت سندباکس است."
    elif gateway == "zarinpal":
        gw_ok, gw_detail = True, "زرین‌پال (واقعی) فعال است."
    else:
        gw_ok, gw_detail = False, f"درگاه ناشناخته: {gateway}"

    if not settings.SMS_ENABLED:
        sms_ok, sms_detail = False, "پیامک غیرفعال است (SMS_ENABLED=0)."
    elif (settings.SMS_PROVIDER or "").strip().lower() in {"", "console"}:
        sms_ok, sms_detail = False, "ارائه‌دهندهٔ پیامک واقعی تنظیم نشده (console)."
    elif settings.SMS_PROVIDER.strip().lower() == "kavenegar" and not settings.KAVENEGAR_API_KEY:
        sms_ok, sms_detail = False, "کلید API کاوه‌نگار خالی است."
    else:
        sms_ok, sms_detail = True, f"پیامک از طریق {settings.SMS_PROVIDER} فعال است."

    from apps.core.models import SiteSettings

    site = SiteSettings.load()
    site_ok = bool((site.phone or "").strip() and (site.address or "").strip())

    return [
        {"id": "gateway", "label": "درگاه پرداخت", "ok": gw_ok, "detail": gw_detail},
        {"id": "sms", "label": "سامانهٔ پیامک", "ok": sms_ok, "detail": sms_detail},
        {
            "id": "two_factor", "label": "ورود دو مرحله‌ای مدیر",
            "ok": bool(settings.ADMIN_2FA_REQUIRED),
            "detail": (
                "ADMIN_2FA_REQUIRED فعال است." if settings.ADMIN_2FA_REQUIRED
                else "ورود دو مرحله‌ای غیرفعال است (توصیه می‌شود فعال شود)."
            ),
        },
        {
            "id": "site_profile", "label": "تلفن و نشانی فروشگاه",
            "ok": site_ok,
            "detail": (
                "تلفن و نشانی در «تنظیمات سایت» تکمیل شده." if site_ok
                else "تلفن یا نشانی فروشگاه در «تنظیمات سایت» خالی است."
            ),
        },
        {
            "id": "https", "label": "HTTPS",
            "ok": _env_bool("HTTPS_ENABLED", False),
            "detail": (
                "HTTPS_ENABLED فعال است." if _env_bool("HTTPS_ENABLED", False)
                else "HTTPS_ENABLED=1 نشده (سایت پشت TLS نیست)."
            ),
        },
        {
            "id": "debug", "label": "حالت اشکال‌زدایی",
            "ok": not settings.DEBUG,
            "detail": "DEBUG خاموش است." if not settings.DEBUG else "DEBUG روشن است -- برای راه‌اندازی خاموشش کنید.",
        },
        {
            "id": "admin_url", "label": "نشانی ورود به پنل",
            "ok": os.environ.get("ADMIN_URL", "admin/").strip() not in {"", "admin/", "admin"},
            "detail": (
                "ADMIN_URL از مقدار پیش‌فرض تغییر کرده."
                if os.environ.get("ADMIN_URL", "admin/").strip() not in {"", "admin/", "admin"}
                else "ADMIN_URL هنوز پیش‌فرض (admin/) است؛ یک مسیر اختصاصی بگذارید."
            ),
        },
    ]


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def build_payload(days: int) -> dict:
    """Compute the full dashboard payload (only called on cache miss)."""
    days = 30 if int(days) == 30 else 14
    today = _tehran_today()

    kpis = {}
    for key, span in (("today", 1), ("week", 7), ("month", 30)):
        start, prev_start, end = _period(span)
        kpis[key] = _kpi_block(start, prev_start, end)
    kpi_list = [
        {"key": key, "title": title, **kpis[key]}
        for key, title in (
            ("today", "امروز"), ("week", "۷ روز اخیر"), ("month", "۳۰ روز اخیر"),
        )
    ]

    chart = _chart(days)
    chart_max = max((p["gross"] for p in chart), default=0)
    # Pre-computed SVG bar geometry (baseline y=140, label row y=162).
    bar_area = 120
    for index, point in enumerate(chart):
        height = round(point["gross"] / chart_max * bar_area) if chart_max else 0
        if height == 0 and point["gross"]:
            height = 2  # keep a sliver visible for tiny-but-nonzero days
        point["bar_h"] = height
        point["bar_y"] = 140 - height
        point["x"] = index * 36 + 6

    payload = {
        "generated_at": timezone.now(),
        "today": today,
        "kpis": kpis,
        "kpi_list": kpi_list,
        "actions": _action_cards(today),
        "chart_days": days,
        "chart": chart,
        "chart_max": chart_max,
        "chart_width": days * 36,
        "top_products": _top_products(days),
        "latest_orders": _latest_orders(),
        "latest_logs": _latest_logs(),
        "readiness": readiness_checks(),
    }
    return payload


def get_dashboard(days: int = 14) -> dict:
    """Cached dashboard payload; ~60s TTL, plain data (Redis-safe)."""
    days = 30 if int(days) == 30 else 14
    key = CACHE_KEY.format(days=days)
    payload = cache.get(key)
    if payload is None:
        payload = build_payload(days)
        cache.set(key, payload, CACHE_SECONDS)
    return payload
