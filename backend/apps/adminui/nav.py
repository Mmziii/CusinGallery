"""Sidebar navigation model for the admin theme (A3).

Groups the apps that ``AdminSite.each_context()`` hands over (already
permission-filtered) into Persian-language sections with sprite icons.
Pure presentation: nothing here queries the database or changes access.

Ordering (owner's workflow, not Django's alphabetical app list)
-------------------------------------------------------------
The sidebar used to be grouped by APP -- «محصولات و کاتالوگ»، «سفارش‌ها و
پرداخت»، … -- which put «محصولات» above «سفارش‌ها» and buried «تنظیمات
فروشگاه» at the bottom, and made the owner open a group to reach the one
thing they came for. It is now a flat list in the order the owner actually
works:

    داشبورد، سفارش‌ها، محصولات، دسته‌بندی‌ها، برندها، کوپن‌ها، نظرات،
    بنرها و پیشنهاد روزانه، اطلاع‌رسانی موجودی، کاربران، محتوا و ظاهر سایت،
    صفحات اطلاعاتی

Everything else (payments, addresses, carts, wishlist, OTP devices, groups,
sessions, product variants/attributes, …) is collapsed into one
«سایر / پیشرفته» group at the bottom: needed sometimes, but never on the
daily path, and never in the way.
"""
from __future__ import annotations

from django.urls import NoReverseMatch, reverse

# --------------------------------------------------------------------------
# The primary items, in the owner's order.
# (app_label, model_name, Persian label, icon, advanced?)
# ``model_name`` is matched case-insensitively against ``object_name``.
# An entry may carry several models: «بنرها و پیشنهاد روزانه» is one item in
# the owner's mental model but two changelists behind it.
# --------------------------------------------------------------------------
PRIMARY_ITEMS: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("orders", ("order",), "سفارش‌ها", "receipt"),
    ("products", ("product",), "محصولات", "box"),
    ("categories", ("category",), "دسته‌بندی‌ها", "tree"),
    ("products", ("brand",), "برندها", "award"),
    ("discounts", ("coupon",), "کوپن‌ها", "ticket"),
    ("reviews", ("review",), "نظرات", "star"),
    # Banner + daily deal: one shelf in the shop, one entry in the menu.
    ("banners", ("banner", "dailydeal"), "بنرها و پیشنهاد روزانه", "megaphone"),
    ("products", ("backinstocksubscription",), "اطلاع‌رسانی موجودی", "bell-ring"),
    ("accounts", ("user",), "کاربران", "users"),
    ("core", ("sitesettings",), "محتوا و ظاهر سایت", "sliders"),
    ("core", ("infopage",), "صفحات اطلاعاتی", "info"),
)

#: Admin-panel pages that are not a model changelist, in the owner's
#: order (shown right after the dashboard link). Each carries the
#: permission that makes it visible; the page enforces the same check.
# (label, url name, icon, required permission)
PRIMARY_EXTRAS: tuple[tuple[str, str, str, str], ...] = (
    ("گزارش‌ها و تحلیل", "admin_reports", "chart-bar", "analytics.view_event"),
)

#: The collapsed bucket at the bottom for everything not listed above.
ADVANCED_GROUP_ID = "advanced"
ADVANCED_GROUP_TITLE = "سایر / پیشرفته"
ADVANCED_GROUP_ICON = "grid"

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
    ("core", "infopage"): "info",
    ("auth", "group"): "shield",
    ("otp_totp", "totpdevice"): "shield",
    ("otp_static", "staticdevice"): "shield",
}

FALLBACK_ICON = "dot"

# Per-model Persian labels for the collapsed group. Django's verbose_name
# is what the model author wrote ("TOTP device", "Wishlist item", …); the
# rest of THIS menu is Persian, so those would stand out as English.
MODEL_LABELS: dict[tuple[str, str], str] = {
    ("payments", "payment"): "پرداخت‌ها",
    ("accounts", "address"): "نشانی‌ها",
    ("cart", "cart"): "سبدهای خرید",
    ("wishlist", "wishlistitem"): "علاقه‌مندی‌ها",
    ("discounts", "couponusage"): "گزارش استفاده از کوپن",
    ("products", "productvariant"): "انواع کالا",
    ("products", "productattribute"): "ویژگی‌های کالا",
    ("products", "productattributevalue"): "مقدارهای ویژگی",
    ("products", "frequentlyboughttogether"): "خریدهای مکمل",
    ("notifications", "notificationlog"): "گزارش اعلان‌ها",
    ("core", "infopage"): "صفحات اطلاعاتی",
    ("auth", "group"): "گروه‌های دسترسی",
    ("otp_totp", "totpdevice"): "دستگاه‌های تأیید دو مرحله‌ای",
    ("otp_static", "staticdevice"): "کدهای پشتیبان",
}


def icon_for(app_label: str, model_name: str) -> str:
    return MODEL_ICONS.get((app_label, model_name.lower()), FALLBACK_ICON)


def label_for(app_label: str, model_name: str, fallback: str) -> str:
    return MODEL_LABELS.get((app_label, model_name.lower()), fallback)


def _admin_index_url() -> str:
    try:
        return reverse("admin:index")
    except NoReverseMatch:
        return "/admin/"


def _model_entry(app_label: str, model: dict, current_path: str, name=None) -> dict:
    url = model.get("admin_url") or ""
    object_name = model.get("object_name") or ""
    return {
        "name": name or label_for(app_label, object_name, model.get("name", "")),
        "object_name": object_name,
        "model_name": object_name.lower(),
        "app_label": app_label,
        "url": url,
        "add_url": model.get("add_url"),
        "icon": icon_for(app_label, object_name),
        "active": bool(url) and current_path.startswith(url),
    }


def build_sidebar(available_apps, request) -> dict:
    """Turn ``available_apps`` into the ordered sidebar structure.

    Returns ``{"primary": [...], "advanced": {...}}`` where each primary
    entry is a flat link (``{"label", "url", "icon", "active", ...}``) or,
    when one entry covers several models, a small group with ``children``.

    ``active`` is derived from ``request.path`` so the current section is
    highlighted and can be scrolled into view (theme.js). Permission
    filtering already happened upstream, so a model the user may not see
    never appears here at all.
    """
    current_path = getattr(request, "path", "") if request is not None else ""

    # object_name (lower) -> model dict, for every accessible model.
    by_key: dict[tuple[str, str], dict] = {}
    for app in available_apps:
        app_label = app["app_label"]
        for model in app.get("models", []):
            key = (app_label, (model.get("object_name") or "").lower())
            by_key[key] = {"app_label": app_label, "model": model}

    primary: list[dict] = []
    taken: set[tuple[str, str]] = set()

    # Non-model admin pages (the reports page) come first, right after the
    # dashboard link. Permission is checked here as well as in the view.
    user = getattr(request, "user", None)
    for label, url_name, icon, perm in PRIMARY_EXTRAS:
        if user is None or not getattr(user, "is_authenticated", False):
            continue
        if perm and not user.has_perm(perm):
            continue
        try:
            url = reverse(url_name)
        except NoReverseMatch:  # pragma: no cover - defensive
            continue
        primary.append({
            "id": url_name,
            "label": label,
            "name": label,
            "url": url,
            "add_url": None,
            "icon": icon,
            "active": bool(url) and current_path.startswith(url),
        })

    for app_label, model_names, label, icon in PRIMARY_ITEMS:
        found = [
            (app_label, name, by_key[(app_label, name)])
            for name in model_names
            if (app_label, name) in by_key
        ]
        if not found:
            continue
        taken.update({(a, n) for a, n, _ in found})

        if len(found) == 1:
            entry = _model_entry(app_label, found[0][2]["model"], current_path)
            entry["label"] = label
            entry["icon"] = icon
            primary.append(entry)
            continue

        # Several models behind one menu entry: keep them as children so
        # the entry stays one row, and mark it active when any child is.
        children = [
            _model_entry(a, data["model"], current_path) for a, _n, data in found
        ]
        primary.append({
            "id": f"{app_label}-{'-'.join(n for _a, n, _d in found)}",
            "label": label,
            "icon": icon,
            "children": children,
            "active": any(child["active"] for child in children),
        })

    advanced_models = [
        _model_entry(app_label, data["model"], current_path)
        for (app_label, model_name), data in by_key.items()
        if (app_label, model_name) not in taken
    ]
    advanced_models.sort(key=lambda item: item["name"])

    return {
        "dashboard_url": _admin_index_url(),
        "primary": primary,
        "advanced": {
            "id": ADVANCED_GROUP_ID,
            "title": ADVANCED_GROUP_TITLE,
            "icon": ADVANCED_GROUP_ICON,
            "models": advanced_models,
            "active": any(item["active"] for item in advanced_models),
        },
    }
