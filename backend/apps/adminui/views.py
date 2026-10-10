"""Staff-only global quick-search JSON endpoint (B6).

Mounted inside the admin URL prefix (see config/urls.py) as
``admin_quick_search``. Returns grouped results (orders, products,
customers, admin sections) for the Ctrl+K palette in the theme shell.

Guarantees:
* staff-only (``staff_member_required``) + per-model ``view_*`` permission
  checks before any queryset runs;
* the same Persian normalizer as storefront search
  (``apps.products.search.normalize_text`` -- Arabic ي/ك, Persian digits,
  ZWNJ, diacritics);
* hard result caps per group and a fixed-window per-user throttle
  (60 req/min -> HTTP 429) implemented with the project cache.
"""
from __future__ import annotations

import re
import time

from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.adminui.templatetags.adminui_extras import group_thousands, to_fa_digits
from apps.accounts.models import User
from apps.orders.models import Order
from apps.products.models import Product
from apps.products.search import normalize_text

MAX_RESULTS_PER_GROUP = 5
MIN_QUERY_LENGTH = 2
THROTTLE_WINDOW_SECONDS = 60
THROTTLE_MAX_REQUESTS = 60

_DIGIT_RUNS = re.compile(r"\d{4,}")

# label, url name, required permission (None = any staff)
SECTIONS = (
    ("داشبورد", "admin:index", None),
    ("سفارش‌ها", "admin:orders_order_changelist", "orders.view_order"),
    ("محصولات", "admin:products_product_changelist", "products.view_product"),
    ("دسته‌بندی‌ها", "admin:categories_category_changelist", "categories.view_category"),
    ("مشتریان", "admin:accounts_user_changelist", "accounts.view_user"),
    ("پرداخت‌ها", "admin:payments_payment_changelist", "payments.view_payment"),
    ("کوپن‌ها", "admin:discounts_coupon_changelist", "discounts.view_coupon"),
    ("بنرها", "admin:banners_banner_changelist", "banners.view_banner"),
    ("نظرات", "admin:reviews_review_changelist", "reviews.view_review"),
    ("اعلان‌ها", "admin:notifications_notificationlog_changelist",
     "notifications.view_notificationlog"),
    ("تنظیمات سایت", "admin:core_sitesettings_changelist", "core.view_sitesettings"),
)


def _throttled(user) -> bool:
    key = f"adminui:qs:{user.pk}:{int(time.time()) // THROTTLE_WINDOW_SECONDS}"
    cache.add(key, 0, THROTTLE_WINDOW_SECONDS * 2)
    try:
        count = cache.incr(key)
    except ValueError:  # pragma: no cover - race with window rollover
        count = 0
    return count > THROTTLE_MAX_REQUESTS


def _jalali(value) -> str:
    from apps.adminui.jalali import format_jalali

    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value, timezone.get_current_timezone())
    return format_jalali(value)


def _money(value) -> str:
    return f"{to_fa_digits(group_thousands(value or 0))} تومان"


def _search_orders(user, norm: str, digits: list[str]) -> list[dict]:
    query = Q(order_number__icontains=norm) | Q(user__username__icontains=norm)
    for d in digits:
        query |= Q(shipping_phone__contains=d)
        query |= Q(user__phone__contains=d)
    rows = (
        Order.objects.filter(query)
        .select_related("user")
        .order_by("-created_at")[:MAX_RESULTS_PER_GROUP]
    )
    results = []
    for o in rows:
        results.append({
            "title": o.order_number,
            "subtitle": " · ".join(filter(None, [
                o.get_status_display(),
                _money(o.total),
                _jalali(o.created_at),
            ])),
            "url": reverse("admin:orders_order_change", args=[o.pk]),
        })
    return results


def _search_products(user, norm: str) -> list[dict]:
    tokens = [t for t in norm.split() if t]
    # Storefront semantics: every normalized token must appear in the
    # pre-normalized search_text (AND); a raw SKU substring also matches.
    query = Q(sku__icontains=norm)
    if tokens:
        token_query = Q()
        for token in tokens:
            token_query &= Q(search_text__icontains=token)
        query |= token_query
    rows = (
        Product.objects.filter(query)
        .order_by("-is_featured", "-updated_at")[:MAX_RESULTS_PER_GROUP]
    )
    results = []
    for p in rows:
        results.append({
            "title": p.name,
            "subtitle": " · ".join(filter(None, [p.sku, _money(p.price)])),
            "url": reverse("admin:products_product_change", args=[p.pk]),
        })
    return results


def _search_customers(user, norm: str, raw: str, digits: list[str]) -> list[dict]:
    query = (
        Q(username__icontains=norm)
        | Q(phone__icontains=norm)
        | Q(email__icontains=norm)
        | Q(first_name__icontains=norm) | Q(last_name__icontains=norm)
        | Q(first_name__icontains=raw) | Q(last_name__icontains=raw)
    )
    for d in digits:
        query |= Q(phone__contains=d)
        query |= Q(username__contains=d)
    rows = (
        User.objects.filter(query, is_staff=False)
        .order_by("-date_joined")[:MAX_RESULTS_PER_GROUP]
    )
    results = []
    for u in rows:
        name = f"{u.first_name} {u.last_name}".strip() or u.username
        results.append({
            "title": name,
            "subtitle": " · ".join(filter(None, [u.phone or u.username, u.email])),
            "url": reverse("admin:accounts_user_change", args=[u.pk]),
        })
    return results


def _search_sections(user, norm: str) -> list[dict]:
    results = []
    for label, url_name, perm in SECTIONS:
        if perm and not user.has_perm(perm):
            continue
        label_norm = normalize_text(label)
        if norm not in label_norm and label_norm not in norm:
            continue
        try:
            results.append({"title": label, "subtitle": "بخش مدیریت", "url": reverse(url_name)})
        except NoReverseMatch:  # pragma: no cover - defensive
            continue
    return results[:MAX_RESULTS_PER_GROUP]


@staff_member_required
def quick_search(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    user = request.user
    if _throttled(user):
        return JsonResponse(
            {"detail": "تعداد درخواست‌ها زیاد است؛ چند لحظه صبر کنید."},
            status=429,
        )

    raw = (request.GET.get("q") or "").strip()
    norm = normalize_text(raw)
    groups: list[dict] = []
    if len(norm) >= MIN_QUERY_LENGTH:
        digits = _DIGIT_RUNS.findall(norm)
        if user.has_perm("orders.view_order"):
            results = _search_orders(user, norm, digits)
            if results:
                groups.append({"id": "orders", "label": "سفارش‌ها", "results": results})
        if user.has_perm("products.view_product"):
            results = _search_products(user, norm)
            if results:
                groups.append({"id": "products", "label": "محصولات", "results": results})
        if user.has_perm("accounts.view_user"):
            results = _search_customers(user, norm, raw, digits)
            if results:
                groups.append({"id": "customers", "label": "مشتریان", "results": results})
        results = _search_sections(user, norm)
        if results:
            groups.append({"id": "sections", "label": "بخش‌های پنل", "results": results})

    return JsonResponse({"query": raw, "groups": groups})
