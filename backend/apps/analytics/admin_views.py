"""Staff-only «گزارش‌ها و تحلیل» page, its exports and the print view.

Mounted inside the admin URL prefix (config/urls.py) so the page uses the
same branded admin shell as every other panel page. Access is enforced
here, not in the template:

* anonymous -> redirect to the admin login;
* authenticated non-staff, or staff without ``analytics.view_event``
  -> HTTP 403;
* each section additionally needs its own model permission, and so does
  its export (see SECTION_PERMS).
"""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.adminui.templatetags.adminui_extras import group_thousands, to_fa_digits

from .exports import (
    SECTION_TITLES,
    csv_bytes,
    csv_response,
    file_stem,
    section_table,
    xlsx_bytes,
    xlsx_response,
)
from .reports import build_report, resolve_range

REPORTS_PERM = "analytics.view_event"

#: Extra model permission each section needs (the reports page itself
#: always needs ``analytics.view_event``).
SECTION_PERMS: dict[str, str] = {
    "summary": "orders.view_order",
    "funnel": "orders.view_order",
    "abandoned": "orders.view_order",
    "products_best": "products.view_product",
    "products_viewed": "products.view_product",
    "products_lowconv": "products.view_product",
    "products_cart": "products.view_product",
    "products_wishlist": "products.view_product",
    "searches_top": REPORTS_PERM,
    "searches_zero": REPORTS_PERM,
    "customers_top": "accounts.view_user",
    "customers_places": "orders.view_order",
    "coupons": "discounts.view_coupon",
    "chart": "orders.view_order",
}


def can_view_reports(user) -> bool:
    return bool(
        user is not None
        and getattr(user, "is_active", False)
        and getattr(user, "is_staff", False)
        and user.has_perm(REPORTS_PERM)
    )


def can_view_section(user, section: str) -> bool:
    perm = SECTION_PERMS.get(section)
    return bool(perm and user.has_perm(perm))


def reports_access_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.is_active:
            return redirect_to_login(
                request.get_full_path(), login_url=reverse("admin:login"),
            )
        if not can_view_reports(user):
            raise PermissionDenied("دسترسی به گزارش‌ها برای این حساب مجاز نیست.")
        return view(request, *args, **kwargs)

    return wrapper


def _section_flags(user) -> dict:
    return {
        "orders": user.has_perm("orders.view_order"),
        "products": user.has_perm("products.view_product"),
        "customers": user.has_perm("accounts.view_user"),
        "coupons": user.has_perm("discounts.view_coupon"),
    }


@require_GET
@reports_access_required
def reports_view(request):
    range_ = resolve_range(request.GET)
    report = build_report(range_)
    export_query = (
        f"range={report['range']['key']}"
        f"&start={report['range']['start_input']}"
        f"&end={report['range']['end_input']}"
    )
    return render(request, "analytics/reports.html", {
        "report": report,
        "range": report["range"],
        "export_query": export_query,
        "can": _section_flags(request.user),
        "reports_url": reverse("admin_reports"),
        "export_url": reverse("admin_reports_export"),
        "print_url": reverse("admin_reports_print"),
        "title": "گزارش‌ها و تحلیل",
    })


@require_GET
@reports_access_required
def reports_export(request):
    section = (request.GET.get("section") or "").strip()
    fmt = (request.GET.get("format") or "xlsx").strip().lower()
    if section not in SECTION_TITLES:
        raise Http404("بخش گزارش ناشناخته است.")
    if not can_view_section(request.user, section):
        raise PermissionDenied("دسترسی به خروجی این بخش مجاز نیست.")
    if fmt not in {"xlsx", "csv"}:
        raise Http404("قالب خروجی ناشناخته است.")

    range_ = resolve_range(request.GET)
    report = build_report(range_)
    table = section_table(report, section)
    stem = file_stem(f"analytics-{section}", report["range"])

    if fmt == "csv":
        return csv_response(
            csv_bytes(table["headers"], table["rows"]),
            f"{stem}.csv",
        )
    data, _written = xlsx_bytes(
        table["headers"], table["rows"],
        sheet_title=table["title"],
        numeric_columns=table["numeric"],
    )
    return xlsx_response(data, f"{stem}.xlsx")


def _print_cell(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "بله" if value else "خیر"
    if isinstance(value, int):
        return to_fa_digits(group_thousands(value))
    return to_fa_digits(str(value))


@require_GET
@reports_access_required
def reports_print(request):
    range_ = resolve_range(request.GET)
    report = build_report(range_)
    tables = []
    for key, title in SECTION_TITLES.items():
        if not can_view_section(request.user, key):
            continue
        table = section_table(report, key)
        tables.append({
            "key": key,
            "title": table["title"],
            "headers": table["headers"],
            "rows": [[_print_cell(value) for value in row] for row in table["rows"]],
            "numeric": table["numeric"],
        })
    return render(request, "analytics/reports_print.html", {
        "report": report,
        "range": report["range"],
        "tables": tables,
        "title": "نسخهٔ چاپی گزارش‌ها",
    })

