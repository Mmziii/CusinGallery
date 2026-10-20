"""
The ONE public payload every storefront surface reads (content + theme).

Building it in one place has three benefits:

* the admin and the storefront can never disagree about which field is
  public -- this module is an explicit allowlist, not a serializer that
  dumps a model;
* the result is cached once (Django cache) and invalidated by a post_save /
  post_delete signal on every contributing model, so a save in the admin is
  visible on the next page load without a restart;
* the backend-rendered SPA shell can inline the theme variables from the
  same cached payload, which is what makes the first paint use the owner's
  colors (no flash of the old theme).

Placeholders are filtered through ``placeholders.clean_value`` exactly like
the old /site/settings/ endpoint: the seeded «+98 21 0000 0000» and any
bracketed instruction in the database must never reach a customer.
"""
from __future__ import annotations

import re

from django.core.cache import cache

from . import theme as theme_module
from .placeholders import clean_value
from .sanitize import sanitize_embed, sanitize_html

CONTENT_CACHE_KEY = "core:site-content:v1"
INFO_PAGE_CACHE_KEY = "core:info-page:v1:{slug}"

#: Long-lived: the post_save signal is the invalidation mechanism, not the
#: timeout. A day is only a safety net for a cache backend that dropped the
#: delete (e.g. a Redis eviction under memory pressure).
CONTENT_CACHE_TIMEOUT = 60 * 60 * 24


def _text(value) -> str:
    """Display value: placeholders and whitespace normalised to ""."""
    return clean_value(value)


def _image_url(field) -> str:
    if not field:
        return ""
    try:
        return field.url or ""
    except (ValueError, AttributeError):  # pragma: no cover - defensive
        return ""


def _path_or_url(value) -> str:
    """A safe internal path or an absolute http(s) URL ("" otherwise)."""
    text = _text(value)
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "/")):
        return text
    return ""


def _handle(value) -> str:
    return _text(value).lstrip("@").strip()


def _social_url(kind: str, value) -> str:
    """Normalise a stored *handle or link* into the channel's real URL."""
    text = _text(value)
    if not text:
        return ""
    if text.lower().startswith(("http://", "https://")):
        return text
    handle = text.lstrip("@").strip()
    if not handle:
        return ""
    templates = {
        "instagram": "https://instagram.com/{handle}",
        "telegram": "https://t.me/{handle}",
        "eitaa": "https://eitaa.com/{handle}",
        "bale": "https://ble.ir/{handle}",
    }
    if kind == "whatsapp":
        digits = re.sub(r"\D", "", text)
        return f"https://wa.me/{digits}" if digits else ""
    template = templates.get(kind)
    return template.format(handle=handle) if template else ""


def _phones(site) -> list[str]:
    phones = []
    first = _text(site.phone)
    if first:
        phones.append(first)
    extra = site.extra_phones or ""
    for chunk in re.split(r"[\n،,]+", extra):
        value = _text(chunk)
        if value and value not in phones:
            phones.append(value)
    return phones


def _brand(site) -> dict:
    return {
        "name": _text(site.site_name) or "کازین گالری",
        "tagline": _text(site.tagline),
        "logo_light": _image_url(site.logo_light),
        "logo_dark": _image_url(site.logo_dark),
        "favicon": _image_url(site.favicon),
    }


def _home(site) -> dict:
    return {
        "heading": _text(site.home_heading),
        "hero": {
            "title": _text(site.hero_title),
            "subtitle": _text(site.hero_subtitle),
            "button_text": _text(site.hero_button_text),
            "button_link": _path_or_url(site.hero_button_link) or "/shop/",
        },
        "sections": {
            "categories": _text(site.section_categories_title),
            "deals": _text(site.section_deals_title),
            "featured": _text(site.section_featured_title),
            "new": _text(site.section_new_title),
            "best_sellers": _text(site.section_best_title),
            "reviews": _text(site.section_reviews_title),
        },
        "story": {
            "title": _text(site.story_title),
            "text": _text(site.story_text),
        },
    }


def _trust_strip(site) -> list[dict]:
    from .models import TrustStripItem

    items = TrustStripItem.objects.filter(site_id=site.pk, is_active=True).order_by(
        "ordering", "pk"
    )
    return [
        {"icon": item.icon, "label": clean_value(item.label)}
        for item in items
        if clean_value(item.label)
    ]


def _footer(site) -> dict:
    socials = {}
    for key in ("instagram", "telegram", "whatsapp", "eitaa", "bale"):
        url = _social_url(key, getattr(site, key, ""))
        if url:
            socials[key] = url
    return {
        "about": _text(site.footer_about),
        "phones": _phones(site),
        "email": _text(site.email),
        "address": _text(site.address),
        "working_hours": _text(site.working_hours),
        "socials": socials,
        "enamad_html": sanitize_embed(_text(site.enamad_html)),
        "copyright_text": _text(site.copyright_text),
        "quick_links_title": _text(site.footer_quick_links_title),
        "help_links_title": _text(site.footer_help_links_title),
        "trust_title": _text(site.footer_trust_title),
    }


def _floating(site) -> dict:
    enabled = bool(site.floating_enabled)
    links = []
    if enabled:
        if site.floating_whatsapp:
            href = _social_url("whatsapp", site.whatsapp)
            if href:
                links.append({"key": "whatsapp", "href": href, "icon": "chat",
                              "label": "گفتگو در واتس‌اپ"})
        if site.floating_telegram:
            href = _social_url("telegram", site.telegram)
            if href:
                links.append({"key": "telegram", "href": href, "icon": "send",
                              "label": "پیام در تلگرام"})
        if site.floating_phone:
            first = _text(site.phone)
            if first:
                links.append({"key": "phone", "href": f"tel:{first.replace(' ', '')}",
                              "icon": "phone", "label": "تماس تلفنی"})
        if site.floating_instagram:
            href = _social_url("instagram", site.instagram)
            if href:
                links.append({"key": "instagram", "href": href, "icon": "instagram",
                              "label": "صفحهٔ اینستاگرام"})
    return {
        "enabled": enabled,
        "links": links,
        "show_scroll_top": True,
    }


def _info_pages() -> list[dict]:
    from .models import InfoPage

    pages = InfoPage.objects.filter(is_published=True).order_by("ordering", "pk")
    return [
        {
            "slug": page.slug,
            "path": page.path,
            "title": clean_value(page.title),
            "seo_title": clean_value(page.seo_title),
            "seo_description": clean_value(page.seo_description),
            "updated_at": page.updated_at.isoformat() if page.updated_at else "",
        }
        for page in pages
    ]


def build_content_payload() -> dict:
    """Uncached payload, built from the singleton and its related rows."""
    from .models import SiteSettings

    site = SiteSettings.load()
    return {
        "brand": _brand(site),
        "home": _home(site),
        "trust_strip": _trust_strip(site),
        "footer": _footer(site),
        "floating": _floating(site),
        "theme": theme_module.theme_payload(site),
        "info_pages": _info_pages(),
    }


def get_content_payload() -> dict:
    """The cached public payload (never contains private fields)."""
    payload = cache.get(CONTENT_CACHE_KEY)
    if payload is None:
        payload = build_content_payload()
        cache.set(CONTENT_CACHE_KEY, payload, CONTENT_CACHE_TIMEOUT)
    return payload


def get_info_page(slug: str) -> dict | None:
    """One published info page (body sanitised), or None -> the API 404s."""
    from .models import InfoPage

    key = INFO_PAGE_CACHE_KEY.format(slug=slug)
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    page = InfoPage.objects.filter(slug=slug, is_published=True).first()
    if page is None:
        # Cache the negative answer too: a crawler hitting an unpublished
        # page must not run a query per request.
        cache.set(key, {}, CONTENT_CACHE_TIMEOUT)
        return None
    payload = {
        "slug": page.slug,
        "path": page.path,
        "title": clean_value(page.title),
        "body": sanitize_html(page.body),
        "seo_title": clean_value(page.seo_title),
        "seo_description": clean_value(page.seo_description),
        "updated_at": page.updated_at.isoformat() if page.updated_at else "",
    }
    cache.set(key, payload, CONTENT_CACHE_TIMEOUT)
    return payload


def invalidate_site_cache() -> None:
    """Drop every public site-content cache entry (called from signals)."""
    from .models import INFO_PAGE_SLUGS

    keys = [CONTENT_CACHE_KEY, "orders:shipping_methods:v1"]
    keys += [INFO_PAGE_CACHE_KEY.format(slug=slug) for slug, _label in INFO_PAGE_SLUGS]
    cache.delete_many(keys)


def theme_css_variables() -> dict:
    """The CSS custom properties for the current theme (cached payload)."""
    return (get_content_payload().get("theme") or {}).get("css_variables") or {}
