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
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.discounts.models import Coupon
from apps.notifications.models import NotificationLog
from apps.orders.models import Order
from apps.products.models import BackInStockSubscription, Product
from apps.reviews.models import Review

TEHRAN = ZoneInfo("Asia/Tehran")

#: Persian Jalali month names, for compact axis labels («۲۳ مهر»).
JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)

CACHE_SECONDS = 60
CACHE_KEY = "adminui:dashboard:v3:{days}"

# The periods the dashboard offers. «امروز» (1) is special: it is the only
# one whose chart is HOURLY -- a single daily bar would tell the owner
# nothing about a day they are living through.
PERIODS: tuple[int, ...] = (1, 7, 14, 30, 90)
DEFAULT_PERIOD = 14

#: Persian labels for the switcher, in order.
PERIOD_LABELS: dict[int, str] = {
    1: "امروز",
    7: "۷ روز",
    14: "۱۴ روز",
    30: "۳۰ روز",
    90: "۹۰ روز",
}

#: How many x-axis ticks the chart may show. More than ~7 and the Jalali
#: labels crowd each other until they are unreadable at 1366px.
MAX_CHART_TICKS = 7


#: Cookie holding the owner's chosen period (see context_processors).
PERIOD_COOKIE = "cusin_dash_days"

#: The owner's period is remembered SERVER SIDE, in their session: a
#: choice made on Monday must still be there on Tuesday, from any browser,
#: with or without JavaScript. The cookie below is only read, for an owner
#: who still carries the one the old client-side switcher wrote.
PERIOD_SESSION_KEY = "cusin_dash_days"


def period_cookie_name(user) -> str:
    """Per-user cookie name, so two owners on one browser don't collide."""
    pk = getattr(user, "pk", None)
    return f"{PERIOD_COOKIE}" if pk in (None, "") else f"{PERIOD_COOKIE}_{pk}"


def normalize_days(value, default: int = DEFAULT_PERIOD) -> int:
    """Clamp anything the URL hands over to one of ``PERIODS``."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    return days if days in PERIODS else default

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
    start = _utc_midnight(today)
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
    # «موجودی کم» is a per-product judgement: each Product carries its own
    # آستانهٔ هشدار موجودی کم (default 5). Counting against the global
    # LOW_STOCK_THRESHOLD showed the owner a number that matched neither
    # the badge on the row nor the list the card links to.
    own_threshold = F("low_stock_threshold")

    o = Order.objects.aggregate(
        # Paid orders sit in PENDING until the OWNER confirms them; that is
        # the queue the dashboard must surface first.
        awaiting_confirmation=Count(
            "pk", filter=PAID_Q & Q(status=Order.Status.PENDING),
        ),
        paid_to_process=Count(
            "pk",
            filter=PAID_Q & Q(status__in=[
                Order.Status.CONFIRMED, Order.Status.PROCESSING,
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
            "pk", filter=Q(stock_quantity__lte=own_threshold, stock_quantity__gt=0),
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
            "id": "awaiting_confirmation", "count": o["awaiting_confirmation"],
            "label": "پرداخت‌شده در انتظار تأیید",
            "hint": "پولشان رسیده اما هنوز تأیید نکرده‌اید؛ تا تأیید شما ارسال نمی‌شوند.",
            "icon": "bell", "perm": "orders.view_order",
            "url": f"{orders_url}?queue=awaiting_confirmation",
        },
        {
            "id": "paid_to_process", "count": o["paid_to_process"],
            "label": "تأیید‌شده در حال آماده‌سازی",
            "hint": "تأیید شده‌اند و در حال آماده‌سازی برای ارسال‌اند.",
            "icon": "box", "perm": "orders.view_order",
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
            "hint": "کالاهایی که موجودی‌شان به آستانهٔ هشدار خودشان رسیده (و بیشتر از صفر).",
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

def _hourly_chart() -> list[dict]:
    """Today's sales in 24 Tehran hourly buckets (1 query)."""
    from apps.adminui.jalali import fa_digits, format_jalali

    today = _tehran_today()
    start = _utc_midnight(today)
    end = _utc_midnight(today + dt.timedelta(days=1))
    rows = (
        Order.objects.filter(created_at__gte=start, created_at__lt=end)
        .annotate(hour=TruncHour("created_at", tzinfo=TEHRAN))
        .values("hour")
        .annotate(gross=Sum("total", filter=PAID_Q), orders=Count("pk", filter=PAID_Q))
    )
    by_hour = {row["hour"].hour: row for row in rows if row["hour"]}
    points = []
    for hour in range(24):
        row = by_hour.get(hour)
        points.append({
            "date": today,
            "hour": hour,
            "jlabel": fa_digits(f"{hour:02d}:00"),
            "jfull": f"{format_jalali(today)} — ساعت {fa_digits(f'{hour:02d}')}",
            "gross": (row["gross"] or 0) if row else 0,
            "orders": row["orders"] if row else 0,
        })
    return points


def _daily_chart(days: int) -> list[dict]:
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
            "hour": None,
            "jlabel": fa_digits(f"{jd.jalali_month:02d}/{jd.jalali_day:02d}"),
            # Axis form: «۲۳ مهر» (day + Persian month name). The «۰۷/۱۸»
            # form stays on the bar's tooltip/table row, where there is
            # room for the year too.
            "jaxis": f"{fa_digits(str(jd.jalali_day))} {JALALI_MONTHS[jd.jalali_month - 1]}",
            "jfull": format_jalali(day),
            "gross": (row["gross"] or 0) if row else 0,
            "orders": row["orders"] if row else 0,
        })
    return points


def _chart(days: int) -> list[dict]:
    """Sales series for the selected period.

    «امروز» is hourly -- the owner wants to see the shape of the day
    they are in, and one bar labelled "today" would not tell them
    anything. Every other period is daily.
    """
    return _hourly_chart() if days == 1 else _daily_chart(days)


def _chart_ticks(points: list[dict], step: float, bar_w: float,
                 limit: int = MAX_CHART_TICKS) -> list[dict]:
    """At most ``limit`` evenly spaced x-axis ticks.

    30 daily bars each labelled «۲۳ مهر» overlap into an unreadable smear;
    the axis now shows ~7 evenly spaced ones (always including the first
    and the last) and the full value of every bar stays in the tooltip and
    in the numbers table underneath.
    """
    total = len(points)
    if total <= limit:
        indices = range(total)
    else:
        positions = [round(i * (total - 1) / (limit - 1)) for i in range(limit)]
        indices = sorted(set(positions))
    ticks = []
    for index in indices:
        point = points[index]
        ticks.append({
            "index": index,
            "x": index * step + bar_w / 2,
            # «۲۳ مهر» -- the day and month the owner thinks in.
            "label": point.get("jaxis") or point["jlabel"],
            "jfull": point["jfull"],
        })
    return ticks


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
    from apps.core.placeholders import placeholder_legal_pages

    site = SiteSettings.load()
    # A seeded «+98 21 0000 0000» or a bracketed «[… را از پنل مدیریت وارد
    # کنید]» is a placeholder, NOT content -- the old check only looked at
    # strip() and therefore reported the store's contact info as complete
    # while the storefront was showing a fake phone number.
    missing_profile = site.missing_items()
    required_missing = [item for item in missing_profile if item["required"]]
    optional_missing = [item for item in missing_profile if not item["required"]]
    # ONE sentence, and then the items themselves, once, in the card's
    # sub-list. Spelling them out here as well made the row read the same
    # list twice -- once as a run-on sentence, once as a nested column.
    site_ok = not required_missing
    if site_ok and optional_missing:
        site_detail = (
            "تلفن و نشانی واقعی ثبت شده است؛ "
            "این موارد اختیاری هنوز خالی‌اند."
        )
    elif site_ok:
        site_detail = "تلفن و نشانی در «تنظیمات فروشگاه» تکمیل شده."
    else:
        site_detail = "این موارد در «تنظیمات فروشگاه» هنوز پر نشده است."

    placeholder_pages = placeholder_legal_pages()
    pages_ok = not placeholder_pages

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
            "detail": site_detail,
            "missing": missing_profile,
        },
        {
            "id": "legal_pages", "label": "صفحه‌های حقوقی/اعتماد",
            "ok": pages_ok,
            "detail": (
                "همهٔ صفحه‌ها متن واقعی دارند."
                if pages_ok
                else "متن یا انتشار این صفحه‌ها هنوز کامل نشده است."
            ),
            "missing": placeholder_pages,
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
    days = normalize_days(days)
    today = _tehran_today()

    # «امروز» is always on screen: it is the one number an owner looks at
    # without choosing anything. The second card follows the switcher.
    start, prev_start, end = _period(1)
    kpis = {"today": _kpi_block(start, prev_start, end)}
    start, prev_start, end = _period(days)
    kpis["period"] = _kpi_block(start, prev_start, end)

    kpi_list = [
        {"key": "today", "title": "امروز", **kpis["today"]},
        {"key": "period", "title": PERIOD_LABELS[days], **kpis["period"]},
    ]

    chart = _chart(days)
    chart_max = max((p["gross"] for p in chart), default=0)
    # Pre-computed SVG bar geometry (baseline y=140, label row y=162).
    bar_area = 120
    step = 36 if len(chart) <= 31 else max(12, round(1000 / len(chart)))
    bar_w = max(6, min(24, step - 12))
    for index, point in enumerate(chart):
        height = round(point["gross"] / chart_max * bar_area) if chart_max else 0
        if height == 0 and point["gross"]:
            height = 2  # keep a sliver visible for tiny-but-nonzero days
        point["bar_h"] = height
        point["bar_y"] = 140 - height
        point["x"] = index * step + (step - bar_w) / 2
        point["bar_w"] = bar_w
        # Tooltip: the full Jalali date and the amount in تومان.
        point["gross_toman"] = f"{point['gross']:,} تومان"

    payload = {
        "generated_at": timezone.now(),
        "today": today,
        "kpis": kpis,
        "kpi_list": kpi_list,
        "actions": _action_cards(today),
        "chart_days": days,
        "chart_hourly": days == 1,
        "chart": chart,
        "chart_max": chart_max,
        "chart_width": max(320, len(chart) * step),
        "chart_ticks": _chart_ticks(chart, step, bar_w),
        "periods": [
            {"days": value, "label": PERIOD_LABELS[value], "active": value == days}
            for value in PERIODS
        ],
        "period_label": PERIOD_LABELS[days],
        "top_products": _top_products(days),
        "latest_orders": _latest_orders(),
        "latest_logs": _latest_logs(),
        "readiness": readiness_checks(),
    }
    return payload


def get_dashboard(days: int = DEFAULT_PERIOD) -> dict:
    """Cached dashboard payload; ~60s TTL, plain data (Redis-safe)."""
    days = normalize_days(days)
    key = CACHE_KEY.format(days=days)
    payload = cache.get(key)
    if payload is None:
        payload = build_payload(days)
        cache.set(key, payload, CACHE_SECONDS)
    return payload
