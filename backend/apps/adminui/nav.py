"""Sidebar navigation model for the admin theme (A3).

Groups the apps that ``AdminSite.each_context()`` hands over (already
permission-filtered) into Persian-language sections with sprite icons.
Pure presentation: nothing here queries the database or changes access.
"""
from __future__ import annotations

from django.urls import NoReverseMatch, reverse

# app_label -> (order, group id). Apps missing from the map land in "more".
APP_GROUPS: dict[str, str] = {
    "products": "catalog",
    "categories": "catalog",
    "orders": "sales",
    "payments": "sales",
    "accounts": "customers",
    "cart": "customers",
    "wishlist": "customers",
    "discounts": "marketing",
    "banners": "marketing",
    "reviews": "marketing",
    "notifications": "messages",
    "core": "settings",
    "auth": "settings",
    "django_otp": "settings",
    "sessions": "settings",
}

GROUPS: tuple[tuple[str, str, str], ...] = (
    # (id, Persian title, icon name -- must exist in the sprite)
    ("catalog", "محصولات و کاتالوگ", "box"),
    ("sales", "سفارش‌ها و پرداخت", "receipt"),
    ("customers", "مشتریان", "users"),
    ("marketing", "بازاریابی", "megaphone"),
    ("messages", "پیام‌ها و گزارش‌ها", "bell"),
    ("settings", "تنظیمات", "sliders"),
    ("more", "سایر بخش‌ها", "grid"),
)

# (app_label, model_name) -> icon id in the sprite; fallback "dot".
MODEL_ICONS: dict[tuple[str, str], str] = {
    ("products", "product"): "box",
    ("products", "productvariant"): "variants",
    ("products", "brand"): "award",
    ("products", "productattribute"): "list",
    ("products", "productattributevalue"): "list",
    ("products", "backinstocksubscription"): "bell-ring",
    ("products", "frequentlyboughttogether"): "sparkle",
    ("categories", "category"): "tree",
    ("orders", "order"): "receipt",
    ("payments", "payment"): "wallet",
    ("accounts", "user"): "users",
    ("accounts", "address"): "map-pin",
    ("cart", "cart"): "cart",
    ("wishlist", "wishlistitem"): "heart",
    ("discounts", "coupon"): "ticket",
    ("discounts", "couponusage"): "chart-bar",
    ("banners", "banner"): "megaphone",
    ("banners", "dailydeal"): "zap",
    ("reviews", "review"): "star",
    ("notifications", "notificationlog"): "mail",
    ("core", "sitesettings"): "sliders",
    ("auth", "group"): "shield",
}

FALLBACK_ICON = "dot"


def icon_for(app_label: str, model_name: str) -> str:
    return MODEL_ICONS.get((app_label, model_name.lower()), FALLBACK_ICON)


def _admin_index_url() -> str:
    try:
        return reverse("admin:index")
    except NoReverseMatch:
        return "/admin/"


def build_sidebar(available_apps, request) -> list[dict]:
    """Turn ``available_apps`` into grouped sidebar data.

    Each group: ``{"id", "title", "icon", "active", "open", "models": [...]}``;
    each model: ``{"name", "url", "add_url", "icon", "active", "object_name"}``.
    ``active`` is derived from ``request.path`` so the current section is
    highlighted (A3). Groups with no accessible models are dropped.
    """
    current_path = getattr(request, "path", "") if request is not None else ""
    grouped: dict[str, list[dict]] = {}

    for app in available_apps:
        app_label = app["app_label"]
        group_id = APP_GROUPS.get(app_label, "more")
        for model in app.get("models", []):
            url = model.get("admin_url") or ""
            add_url = model.get("add_url")
            grouped.setdefault(group_id, []).append({
                "name": model.get("name", ""),
                "object_name": model.get("object_name", ""),
                "model_name": (model.get("object_name") or "").lower(),
                "url": url,
                "add_url": add_url,
                "icon": icon_for(app_label, (model.get("object_name") or "")),
                "active": bool(url) and current_path.startswith(url),
            })

    sections: list[dict] = []
    for group_id, title, icon in GROUPS:
        models = grouped.pop(group_id, None)
        if not models:
            continue
        active = any(m["active"] for m in models)
        sections.append({
            "id": group_id,
            "title": title,
            "icon": icon,
            "active": active,
            "open": active,  # active section starts expanded (A3)
            "models": models,
        })

    # Unknown apps (future additions) keep working via the "more" bucket.
    leftovers = [m for models in grouped.values() for m in models]
    if leftovers:
        sections.append({
            "id": "more",
            "title": "سایر بخش‌ها",
            "icon": "grid",
            "active": any(m["active"] for m in leftovers),
            "open": any(m["active"] for m in leftovers),
            "models": leftovers,
        })
    return sections
