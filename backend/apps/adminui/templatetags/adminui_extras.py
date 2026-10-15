"""Template filters/tags for the admin panel (apps.adminui).

Display-only helpers: Jalali dates (B2), Persian digits, Toman money
formatting and the sidebar/icon tags used by the theme shell (A3/A6).
None of these change form inputs, filters or stored data.
"""
from __future__ import annotations

import datetime as _dt

from django import template
from django.utils import timezone
from django.utils.html import format_html

from apps.adminui import admin_dates, jalali
from apps.adminui.breadcrumbs import build_crumbs
from apps.adminui.nav import build_sidebar

register = template.Library()

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_THOUSANDS = "\u066c"  # Persian thousands separator «٬»


def to_fa_digits(value: str) -> str:
    return str(value).translate(_FA_DIGITS)


def group_thousands(number) -> str:
    """Group an int with the Persian thousands separator, ASCII digits."""
    try:
        n = int(number)
    except (TypeError, ValueError):
        return str(number)
    sign = "-" if n < 0 else ""
    digits = f"{abs(n):d}"
    chunks = []
    while digits:
        chunks.append(digits[-3:])
        digits = digits[:-3]
    return sign + _THOUSANDS.join(reversed(chunks))


# ---------------------------------------------------------------------------
# Jalali / Persian-number filters (B2)
# ---------------------------------------------------------------------------

@register.filter(name="jdate")
def jdate_filter(value, arg: str = "") -> str:
    """``{{ order.created_at|jdate }}`` -> ``۱۴۰۵/۰۷/۱۸``.

    Aware datetimes are converted with the active Django timezone before the
    calendar maths, so "today" matches what the owner sees. Pass ``"iso"`` to
    get an ASCII ``JYYY-JMM-JDD`` string (useful inside ``title`` attributes).
    """
    if value in (None, ""):
        return "—"
    if isinstance(value, _dt.datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    if arg == "iso":
        jd = jalali.to_jalali(value)
        return jd.iso_jalali() if jd else "—"
    return jalali.format_jalali(value)


@register.filter(name="jdatetime")
def jdatetime_filter(value) -> str:
    """Jalali date + ``HH:MM`` in the active timezone, Persian digits."""
    if value in (None, ""):
        return "—"
    if isinstance(value, _dt.datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    return jalali.format_jalali_datetime(value)


@register.filter(name="jweekday")
def jweekday_filter(value) -> str:
    """Persian weekday name (شنبه … جمعه)."""
    if value in (None, ""):
        return "—"
    if isinstance(value, _dt.datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    jd = jalali.to_jalali(value)
    return jalali.JALALI_WEEKDAY_NAMES[jd.weekday()] if jd else "—"


@register.filter(name="jdate_range")
def jdate_range_filter(start, end) -> str:
    """A Jalali window: ``۱۴۰۵/۰۷/۲۶`` when both ends are the same day,
    ``۱۴۰۵/۰۷/۲۶ تا ۱۴۰۵/۰۷/۲۸`` otherwise.

    The order change page's «بازهٔ تحویل» used to print the raw ISO dates
    and append a stray «روز», because «تا» was read as a duration.
    """
    return admin_dates.jalali_range(start, end)


@register.filter(name="fanum")
def fanum_filter(value) -> str:
    """Convert digits of a number/string to Persian digits."""
    if value in (None, ""):
        return "—"
    return to_fa_digits(value)


@register.filter(name="toman")
def toman_filter(value, suffix: str = "تومان") -> str:
    """``1234567`` -> ``۱٬۲۳۴٬۵۶۷ تومان`` (grouped, Persian digits)."""
    if value in (None, ""):
        return "—"
    try:
        grouped = group_thousands(int(value))
    except (TypeError, ValueError):
        return str(value)
    text = to_fa_digits(grouped)
    return f"{text} {suffix}" if suffix else text


@register.filter(name="pctfa")
def pctfa_filter(value) -> str:
    """Signed percentage with Persian digits: ``+۱۲٪`` / ``−۸٪`` / ``—``."""
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "—"
    rounded = round(f)
    if rounded == 0:
        return f"{to_fa_digits(0)}٪"
    sign = "+" if rounded > 0 else "−"
    return f"{sign}{to_fa_digits(abs(rounded))}٪"


@register.filter(name="numfa")
def numfa_filter(value) -> str:
    """Integer with Persian thousands separator AND Persian digits."""
    if value in (None, ""):
        return "—"
    return to_fa_digits(group_thousands(value))


# ---------------------------------------------------------------------------
# Icons + sidebar (A3/A6)
# ---------------------------------------------------------------------------

@register.simple_tag
def changelist_page_href(cl, page) -> str:
    """The href for one page of the changelist paginator.

    The overridden admin/pagination.html renders the page links itself so
    the numbers can be Persian; Django has no template tag for exactly
    this URL, and rebuilding it by hand is how query parameters get lost.
    """
    from django.contrib.admin.templatetags.admin_list import PAGE_VAR

    return cl.get_query_string({PAGE_VAR: page})


@register.simple_tag
def cusin_icon(name: str, css_class: str = "cusin-icon") -> str:
    """Render ``<svg><use href="#cusin-i-NAME"/></svg>`` from the inline sprite."""
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="#cusin-i-{}"></use></svg>',
        css_class,
        name,
    )


@register.inclusion_tag("adminui/_breadcrumbs.html", takes_context=True)
def cusin_breadcrumbs(context) -> dict:
    """«شروع › سفارش‌ها › CG-…» -- one trail, no repeated label.

    Django's own admin templates each render their own trail, and a
    single-model app (orders, products, banners) is named after the model
    it contains, so the trail read «سفارش‌ها › سفارش‌ها». The theme builds
    the trail itself and drops the app crumb when it would only repeat
    the model crumb -- see apps/adminui/breadcrumbs.py.
    """
    return {"crumbs": build_crumbs(context)}


@register.inclusion_tag("adminui/_sidebar.html", takes_context=True)
def cusin_sidebar(context) -> dict:
    """Sidebar navigation built from the admin's ``available_apps``.

    ``available_apps`` comes from ``AdminSite.each_context()`` and is already
    permission-filtered, so the menu respects per-user access automatically.

    The result is the owner-ordered flat list plus the collapsed
    «سایر / پیشرفته» bucket -- see apps/adminui/nav.py.
    """
    request = context.get("request")
    available_apps = context.get("available_apps") or []
    index_url = context.get("cusin_index_url") or "/admin/"
    is_index_active = bool(request) and request.path == index_url
    return {
        "sidebar": build_sidebar(available_apps, request),
        "is_index_active": is_index_active,
        "request": request,
    }
