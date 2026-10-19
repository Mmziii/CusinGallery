"""The owner's «گزارش‌ها و تحلیل» data layer.

Every number on the report page comes from a small, fixed set of
aggregate queries (bounded: see ReportQueryBudgetTests), scoped to a
Tehran-day range and expressed with the SAME definitions the dashboard
uses (paid + not cancelled/returned = real money).

Range selection
---------------
``?range=today|7|30|90|year|custom`` plus, for ``custom``,
``&start=1405/07/01&end=1405/07/30`` in JALALI. Dates are validated and
clamped server-side; an unusable custom range falls back to an explicit
Persian message rather than an error page.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.db.models import Count, F, Max, Min, Prefetch, Q, Sum
from django.db.models.functions import Greatest, TruncDate
from django.urls import NoReverseMatch, reverse

from apps.adminui import jalali
from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, OrderItem
from apps.wishlist.models import WishlistItem

from .models import Event

TEHRAN = ZoneInfo("Asia/Tehran")
JALALI_MONTHS = jalali.JALALI_MONTH_NAMES

#: Persian labels for the preset chips, in display order.
PRESETS: tuple[tuple[str, str], ...] = (
    ("today", "امروز"),
    ("7", "۷ روز"),
    ("30", "۳۰ روز"),
    ("90", "۹۰ روز"),
    ("year", "امسال"),
    ("custom", "بازهٔ دلخواه"),
)
PRESET_DAYS = {"7": 7, "30": 30, "90": 90}
DEFAULT_RANGE = "30"
MAX_SPAN_DAYS = 366

PAID = Q(payment_status=Order.PaymentStatus.PAID)
NOT_CANCELLED = ~Q(
    status__in=[Order.Status.CANCELLED, Order.Status.RETURNED],
)
#: Money that counts as a real sale (paid and not cancelled/returned).
SOLD = PAID & NOT_CANCELLED

TOP_LIMIT = 10


# ---------------------------------------------------------------------------
# range selection
# ---------------------------------------------------------------------------

def _fa_to_ascii(value: str) -> str:
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return str(value or "").translate(table)


def _tehran_today(now=None) -> dt.date:
    from django.utils import timezone

    now = now or timezone.now()
    if isinstance(now, dt.datetime):
        if timezone.is_aware(now):
            return timezone.localtime(now, TEHRAN).date()
        return now.date()
    return now


def _utc_midnight(day: dt.date) -> dt.datetime:
    """Start of a Tehran calendar day as an aware UTC datetime."""
    return dt.datetime.combine(day, dt.time.min, tzinfo=TEHRAN).astimezone(dt.timezone.utc)


def parse_jalali(text) -> dt.date | None:
    """``۱۴۰۵/۰۷/۰۱`` (Persian or ASCII digits, / - or .) -> Gregorian date."""
    cleaned = _fa_to_ascii(text).strip().replace("-", "/").replace(".", "/")
    if not cleaned:
        return None
    parts = [part for part in cleaned.split("/") if part.strip()]
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
        if year < 1300 or year > 1500:
            return None
        return jalali.jalali_to_gregorian(year, month, day)
    except (TypeError, ValueError):
        return None


def _jalali_input(value: dt.date) -> str:
    jd = jalali.to_jalali(value)
    return f"{jd.jalali_year:04d}/{jd.jalali_month:02d}/{jd.jalali_day:02d}"


@dataclass(frozen=True)
class ReportRange:
    key: str
    label: str
    start_date: dt.date
    end_date: dt.date
    start: dt.datetime
    end: dt.datetime
    start_input: str
    end_input: str
    message: str = ""

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "start_input": self.start_input,
            "end_input": self.end_input,
            "days": self.days,
        }


def resolve_range(params, now=None) -> ReportRange:
    """Validate ``?range=`` / ``?start=`` / ``?end=`` from a request."""
    params = params or {}
    today = _tehran_today(now)
    key = (params.get("range") or DEFAULT_RANGE).strip().lower()
    if key not in dict(PRESETS):
        key = DEFAULT_RANGE

    message = ""
    if key == "today":
        start_date = end_date = today
        label = "امروز"
    elif key in PRESET_DAYS:
        start_date = today - dt.timedelta(days=PRESET_DAYS[key] - 1)
        end_date = today
        label = dict(PRESETS)[key]
    elif key == "year":
        jd = jalali.to_jalali(today)
        start_date = jalali.jalali_to_gregorian(jd.jalali_year, 1, 1)
        end_date = today
        label = "امسال"
    else:  # custom
        start_date = parse_jalali(params.get("start"))
        end_date = parse_jalali(params.get("end"))
        label = "بازهٔ دلخواه"
        if start_date is None or end_date is None:
            message = "تاریخ بازهٔ دلخواه را به شکل ۱۴۰۵/۰۷/۰۱ وارد کنید؛ بازهٔ ۳۰ روز اخیر نشان داده شد."
            key = DEFAULT_RANGE
            start_date = today - dt.timedelta(days=PRESET_DAYS[DEFAULT_RANGE] - 1)
            end_date = today
            label = dict(PRESETS)[key]
        elif start_date > end_date:
            start_date, end_date = end_date, start_date
            message = "تاریخ شروع بعد از تاریخ پایان بود؛ جای دو تاریخ عوض شد."

    if end_date > today:
        end_date = today
        if not message:
            message = "تاریخ پایان در آینده بود؛ تا امروز محدود شد."
    if start_date > today:
        start_date = today
    if (end_date - start_date).days + 1 > MAX_SPAN_DAYS:
        start_date = end_date - dt.timedelta(days=MAX_SPAN_DAYS - 1)
        message = "بیشترین بازهٔ قابل گزارش یک سال است؛ بازه به یک سال محدود شد."

    end_exclusive = _utc_midnight(end_date + dt.timedelta(days=1))
    return ReportRange(
        key=key,
        label=label,
        start_date=start_date,
        end_date=end_date,
        start=_utc_midnight(start_date),
        end=end_exclusive,
        start_input=_jalali_input(start_date),
        end_input=_jalali_input(end_date),
        message=message,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _pct(part, whole) -> int:
    if not whole:
        return 0
    return round((float(part) / float(whole)) * 100)


def _admin_url(name: str, pk) -> str:
    try:
        return reverse(name, args=[pk])
    except NoReverseMatch:  # pragma: no cover - defensive
        return ""


def _customer_name(row: dict) -> str:
    name = f"{row.get('user__first_name') or ''} {row.get('user__last_name') or ''}".strip()
    return name or row.get("user__username") or "—"


def _jalali_day(value) -> str:
    return jalali.format_jalali(value, persian_digits=False)


def _month_day(value) -> str:
    jd = jalali.to_jalali(value)
    return f"{jd.jalali_day} {JALALI_MONTHS[jd.jalali_month - 1]}"


def _event_queryset(range_: ReportRange):
    return Event.objects.filter(created_at__gte=range_.start, created_at__lt=range_.end)


def _order_queryset(range_: ReportRange):
    return Order.objects.filter(created_at__gte=range_.start, created_at__lt=range_.end)


def _sold_order_queryset(range_: ReportRange):
    return _order_queryset(range_).filter(SOLD)


# ---------------------------------------------------------------------------
# section builders
# ---------------------------------------------------------------------------

def _summary(range_: ReportRange) -> dict:
    orders = _order_queryset(range_).aggregate(
        orders=Count("pk"),
        paid_orders=Count("pk", filter=SOLD),
        revenue=Sum("total", filter=SOLD),
    )
    revenue = orders["revenue"] or 0
    paid_orders = orders["paid_orders"] or 0

    sessions = _event_queryset(range_).aggregate(
        any_sessions=Count(
            "session_key", distinct=True, filter=~Q(session_key=""),
        ),
        paid_sessions=Count(
            "session_key", distinct=True,
            filter=Q(event_type=Event.Type.ORDER_PAID) & ~Q(session_key=""),
        ),
    )

    paid_users = list(
        _sold_order_queryset(range_)
        .values_list("user_id", flat=True)
        .distinct()
    )
    # A customer is NEW when their FIRST paid order (ever) is inside this
    # range; anyone who had already paid before is RETURNING.
    first_paid = dict(
        Order.objects.filter(PAID)
        .values("user_id")
        .annotate(first=Min("created_at"))
        .values_list("user_id", "first")
    )
    new_customers = sum(
        1 for user_id in paid_users
        if first_paid.get(user_id) is not None and first_paid[user_id] >= range_.start
    )
    returning = max(0, len(paid_users) - new_customers)

    return {
        "revenue": revenue,
        "orders": orders["orders"] or 0,
        "paid_orders": paid_orders,
        "aov": round(revenue / paid_orders) if paid_orders else 0,
        "sessions": sessions["any_sessions"] or 0,
        "paid_sessions": sessions["paid_sessions"] or 0,
        "conversion": _pct(sessions["paid_sessions"] or 0, sessions["any_sessions"] or 0),
        "new_customers": new_customers,
        "returning_customers": returning,
        "customers": len(paid_users),
    }


def _funnel(range_: ReportRange) -> list[dict]:
    steps = (
        (Event.Type.PRODUCT_VIEW, "بازدید محصول"),
        (Event.Type.ADD_TO_CART, "افزودن به سبد خرید"),
        (Event.Type.CHECKOUT_STARTED, "شروع تسویه حساب"),
        (Event.Type.ORDER_PLACED, "ثبت سفارش"),
        (Event.Type.ORDER_PAID, "پرداخت سفارش"),
    )
    aggregates = {}
    for event_type, _label in steps:
        aggregates[event_type] = Count(
            "session_key", distinct=True,
            filter=Q(event_type=event_type) & ~Q(session_key=""),
        )
    counts = _event_queryset(range_).aggregate(**aggregates)

    rows = []
    previous = None
    for event_type, label in steps:
        count = counts.get(event_type) or 0
        drop = None
        if previous is not None:
            drop = _pct(max(0, previous - count), previous) if previous else 0
        rows.append({
            "key": event_type,
            "label": label,
            "count": count,
            "drop": drop,
            "of_first": _pct(count, counts.get(Event.Type.PRODUCT_VIEW) or 0),
        })
        previous = count
    return rows


def _abandoned_carts(range_: ReportRange) -> list[dict]:
    """Carts with items whose last activity is inside the range.

    A completed checkout CLEARS the cart (apps.orders.services), so a cart
    that still has items was, by construction, not converted. Carts are
    server-side only (logged-in shoppers); guest carts are reported via
    the add_to_cart events in the funnel instead.
    """
    last_item = Max("items__updated_at")
    carts = (
        Cart.objects.annotate(
            last_activity=Greatest(last_item, F("updated_at")),
            item_count=Count("items"),
            total_value=Sum(F("items__quantity") * F("items__product__price")),
        )
        .filter(item_count__gt=0, last_activity__gte=range_.start, last_activity__lt=range_.end)
        .select_related("user")
        .prefetch_related(
            Prefetch("items", queryset=CartItem.objects.select_related("product")),
        )
        .order_by("-last_activity")[:50]
    )
    rows = []
    for cart in carts:
        user = cart.user
        items = [
            {
                "name": item.product.name,
                "quantity": item.quantity,
                "line_total": item.product.price * item.quantity,
            }
            for item in cart.items.all()
        ]
        name = (user.get_full_name() or "").strip() or user.username
        rows.append({
            "name": name,
            "phone": getattr(user, "phone", "") or "",
            "user_id": user.pk,
            "user_url": _admin_url("admin:accounts_user_change", user.pk),
            "orders_url": f"{reverse('admin:orders_order_changelist')}?user__id__exact={user.pk}",
            "items": items,
            "item_count": sum(item["quantity"] for item in items),
            "total": cart.total_value or 0,
            "last_activity": cart.last_activity,
        })
    return rows


def _best_sellers(range_: ReportRange) -> tuple[list[dict], dict]:
    rows = (
        OrderItem.objects.filter(
            order__payment_status=Order.PaymentStatus.PAID,
            product__isnull=False,
        )
        .filter(
            order__created_at__gte=range_.start,
            order__created_at__lt=range_.end,
        )
        .exclude(order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])
        .values("product_id")
        .annotate(
            name=Max("product_name"),
            qty=Sum("quantity"),
            revenue=Sum("total_price"),
        )
        .order_by("-qty")
    )
    all_rows = list(rows)
    sold_by_product = {row["product_id"]: row for row in all_rows}
    top = []
    for row in all_rows[:TOP_LIMIT]:
        top.append({
            "product_id": row["product_id"],
            "name": row["name"] or "—",
            "url": _admin_url("admin:products_product_change", row["product_id"]),
            "qty": row["qty"] or 0,
            "revenue": row["revenue"] or 0,
        })
    return top, sold_by_product


def _product_events(range_: ReportRange, event_type: str) -> dict:
    rows = (
        _event_queryset(range_)
        .filter(event_type=event_type, product__isnull=False)
        .values("product_id", "product__name")
        .annotate(count=Count("pk"))
    )
    return {
        row["product_id"]: {
            "name": row["product__name"] or "—",
            "count": row["count"],
            "url": _admin_url("admin:products_product_change", row["product_id"]),
        }
        for row in rows
    }


def _products(range_: ReportRange) -> dict:
    best_sellers, sold_by_product = _best_sellers(range_)
    views = _product_events(range_, Event.Type.PRODUCT_VIEW)
    cart_adds = _product_events(range_, Event.Type.ADD_TO_CART)

    most_viewed = sorted(
        ({"product_id": product_id, **row} for product_id, row in views.items()),
        key=lambda row: row["count"],
        reverse=True,
    )[:TOP_LIMIT]

    # «پربازدید ولی کم‌فروش»: at least 5 views and under 2% sold-per-view.
    low_conversion = []
    for product_id, row in views.items():
        if row["count"] < 5:
            continue
        sold = sold_by_product.get(product_id, {}).get("qty", 0) or 0
        conversion = _pct(sold, row["count"])
        if conversion < 2:
            low_conversion.append({
                "product_id": product_id,
                "name": row["name"],
                "url": row["url"],
                "views": row["count"],
                "sold": sold,
                "conversion": conversion,
            })
    low_conversion.sort(key=lambda row: row["views"], reverse=True)
    low_conversion = low_conversion[:TOP_LIMIT]

    # «به سبد رفت ولی خریده نشد»: cart adds that never turned into a sale.
    cart_not_bought = []
    for product_id, row in cart_adds.items():
        sold = sold_by_product.get(product_id, {}).get("qty", 0) or 0
        gap = row["count"] - sold
        if gap <= 0:
            continue
        cart_not_bought.append({
            "product_id": product_id,
            "name": row["name"],
            "url": row["url"],
            "cart_adds": row["count"],
            "sold": sold,
            "gap": gap,
        })
    cart_not_bought.sort(key=lambda row: row["gap"], reverse=True)
    cart_not_bought = cart_not_bought[:TOP_LIMIT]

    wishlisted_rows = (
        WishlistItem.objects.filter(
            created_at__gte=range_.start, created_at__lt=range_.end,
        )
        .values("product_id", "product__name")
        .annotate(count=Count("pk"))
        .order_by("-count")[:TOP_LIMIT]
    )
    most_wishlisted = [
        {
            "product_id": row["product_id"],
            "name": row["product__name"] or "—",
            "url": _admin_url("admin:products_product_change", row["product_id"]),
            "count": row["count"],
        }
        for row in wishlisted_rows
    ]

    return {
        "best_sellers": best_sellers,
        "most_viewed": most_viewed,
        "low_conversion": low_conversion,
        "cart_not_bought": cart_not_bought,
        "most_wishlisted": most_wishlisted,
    }


def _searches(range_: ReportRange) -> dict:
    events = _event_queryset(range_).filter(event_type=Event.Type.SEARCH).exclude(search_query="")
    totals = events.aggregate(
        total=Count("pk"),
        zero=Count("pk", filter=Q(search_results=0)),
    )
    top = [
        {"query": row["search_query"], "count": row["count"]}
        for row in events.values("search_query").annotate(count=Count("pk")).order_by("-count")[:TOP_LIMIT]
    ]
    zero = [
        {"query": row["search_query"], "count": row["count"]}
        for row in (
            events.filter(search_results=0)
            .values("search_query")
            .annotate(count=Count("pk"))
            .order_by("-count")[:TOP_LIMIT]
        )
    ]
    return {
        "top": top,
        "zero": zero,
        "total": totals["total"] or 0,
        "zero_total": totals["zero"] or 0,
    }


def _customers(range_: ReportRange) -> dict:
    paid = _sold_order_queryset(range_)
    top = [
        {
            "user_id": row["user_id"],
            "name": _customer_name(row),
            "phone": row["user__phone"] or "",
            "url": _admin_url("admin:accounts_user_change", row["user_id"]),
            "orders": row["orders"],
            "spend": row["spend"] or 0,
        }
        for row in (
            paid.values(
                "user_id", "user__first_name", "user__last_name",
                "user__phone", "user__username",
            )
            .annotate(orders=Count("pk"), spend=Sum("total"))
            .order_by("-spend")[:TOP_LIMIT]
        )
    ]

    per_customer = list(paid.values("user_id").annotate(orders=Count("pk")))
    repeat = sum(1 for row in per_customer if row["orders"] >= 2)
    buyers = len(per_customer)

    places = list(
        _order_queryset(range_)
        .exclude(shipping_province="")
        .values("shipping_province", "shipping_city")
        .annotate(
            orders=Count("pk"),
            revenue=Sum("total", filter=SOLD),
        )
        .order_by("-orders")
    )
    max_orders = max((row["orders"] for row in places), default=0)
    place_rows = [
        {
            "province": row["shipping_province"] or "—",
            "city": row["shipping_city"] or "—",
            "orders": row["orders"],
            "revenue": row["revenue"] or 0,
            "width": _pct(row["orders"], max_orders),
        }
        for row in places[:15]
    ]

    return {
        "top": top,
        "buyers": buyers,
        "repeat_customers": repeat,
        "repeat_rate": _pct(repeat, buyers),
        "places": place_rows,
        "places_total": sum(row["orders"] for row in places),
    }


def _coupons(range_: ReportRange) -> list[dict]:
    rows = (
        _sold_order_queryset(range_)
        .filter(coupon__isnull=False)
        .values("coupon__code")
        .annotate(uses=Count("pk"), discount=Sum("discount_amount"))
        .order_by("-uses", "-discount")
    )
    return [
        {
            "code": row["coupon__code"],
            "uses": row["uses"],
            "discount": row["discount"] or 0,
        }
        for row in rows
    ]


def _chart(range_: ReportRange) -> dict:
    rows = (
        _order_queryset(range_)
        .annotate(day=TruncDate("created_at", tzinfo=TEHRAN))
        .values("day")
        .annotate(
            orders=Count("pk"),
            revenue=Sum("total", filter=SOLD),
        )
        .order_by("day")
    )
    by_day = {
        row["day"]: {
            "orders": row["orders"],
            "revenue": row["revenue"] or 0,
        }
        for row in rows
    }

    points = []
    day = range_.start_date
    while day <= range_.end_date:
        values = by_day.get(day, {"orders": 0, "revenue": 0})
        points.append({
            "date": day,
            "jfull": jalali.format_jalali(day, persian_digits=False),
            "jaxis": _month_day(day),
            "orders": values["orders"],
            "revenue": values["revenue"],
        })
        day += dt.timedelta(days=1)

    step = 36 if len(points) <= 31 else max(12, round(1000 / len(points)))
    bar_w = max(6, min(24, step - 12))
    rev_max = max((point["revenue"] for point in points), default=0)
    order_max = max((point["orders"] for point in points), default=0)

    for index, point in enumerate(points):
        point["x"] = index * step + (step - bar_w) / 2
        point["bar_w"] = bar_w
        height = round(point["revenue"] / rev_max * 120) if rev_max else 0
        if height == 0 and point["revenue"]:
            height = 2
        point["rev_h"] = height
        point["rev_y"] = 140 - height
        oheight = round(point["orders"] / order_max * 120) if order_max else 0
        if oheight == 0 and point["orders"]:
            oheight = 2
        point["ord_h"] = oheight
        point["ord_y"] = 140 - oheight

    total = len(points)
    limit = 7
    if total <= limit:
        indices = list(range(total))
    else:
        positions = [round(i * (total - 1) / (limit - 1)) for i in range(limit)]
        indices = sorted(set(positions))
    ticks = [
        {"x": points[index]["x"] + bar_w / 2, "label": points[index]["jaxis"]}
        for index in indices
    ]

    return {
        "points": points,
        "ticks": ticks,
        "rev_max": rev_max,
        "order_max": order_max,
        "width": max(320, len(points) * step),
        "bar_w": bar_w,
        "has_data": bool(rev_max or order_max),
    }


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def build_report(range_: ReportRange) -> dict:
    return {
        "range": range_.as_dict(),
        "presets": [
            {"key": key, "label": label, "active": key == range_.key}
            for key, label in PRESETS
        ],
        "message": range_.message,
        "summary": _summary(range_),
        "funnel": _funnel(range_),
        "abandoned": _abandoned_carts(range_),
        "products": _products(range_),
        "searches": _searches(range_),
        "customers": _customers(range_),
        "coupons": _coupons(range_),
        "chart": _chart(range_),
    }
