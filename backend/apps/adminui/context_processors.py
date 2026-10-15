"""RequestContext additions for the admin theme.

Cheap on every request (dict of settings/URLs); the dashboard payload is
computed ONLY for the admin index view and only while the theme is on,
so no other page pays for it.
"""
from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.adminui.dashboard import (
    DEFAULT_PERIOD,
    PERIOD_COOKIE,
    get_dashboard,
    normalize_days,
    period_cookie_name,
)


def _safe_reverse(name: str, default: str = "") -> str:
    try:
        return reverse(name)
    except NoReverseMatch:  # pragma: no cover - defensive during early boot
        return default


def _dashboard_days(request, user) -> int:
    """The period the owner is looking at.

    Priority: an explicit ``?days=`` in the URL (a shared link must win),
    then the cookie the switcher wrote on their last visit, then the
    default. The cookie is per user id, so a shared shop computer does not
    make one owner's «۹۰ روز» the other owner's dashboard.
    """
    from_query = request.GET.get("days")
    if from_query is not None:
        return normalize_days(from_query)
    cookie_name = period_cookie_name(user)
    stored = request.COOKIES.get(cookie_name)
    if stored is not None:
        return normalize_days(stored, default=DEFAULT_PERIOD)
    return DEFAULT_PERIOD


def admin_panel(request):
    ctx = {
        "admin_theme_enabled": bool(settings.ADMIN_THEME_ENABLED),
        "cusin_index_url": _safe_reverse("admin:index", "/admin/"),
        "cusin_quick_search_url": _safe_reverse("admin_quick_search"),
        "cusin_frontend_url": settings.FRONTEND_URL,
    }
    resolver = getattr(request, "resolver_match", None)
    if (
        settings.ADMIN_THEME_ENABLED
        and resolver is not None
        and resolver.app_name == "admin"
        and resolver.url_name == "index"
    ):
        user = request.user
        days = _dashboard_days(request, user)
        payload = get_dashboard(days)
        ctx["cusin_dashboard"] = payload
        ctx["cusin_dashboard_days"] = days
        # Per-model permission gating (B1): cards are hidden here; the URLs
        # they point at are stock admin changelists and enforce access too.
        ctx["cusin_actions"] = [
            card for card in payload["actions"]
            if not card["perm"] or user.has_perm(card["perm"])
        ]
        ctx["cusin_readiness"] = payload["readiness"] if user.is_superuser else []
        ctx["cusin_perms"] = {
            "orders": user.has_perm("orders.view_order"),
            "products": user.has_perm("products.view_product"),
            "customers": user.has_perm("accounts.view_user"),
        }
    return ctx
