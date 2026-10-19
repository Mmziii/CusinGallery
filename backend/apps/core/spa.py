"""
Real HTTP status for storefront page URLs (Audit 19 item 5).

The problem: nginx answered EVERY page path with the built React shell
(``try_files $uri $uri/ /index.html`` in the frontend container), so
``/nonexistent-xyz`` and ``/products/does-not-exist/`` returned **200** with
the 404 design -- a soft 404. Search engines index those URLs, and a broken
link looks healthy to every monitoring tool.

The fix keeps the architecture ("nginx in front, React SPA behind") and moves
the DECISION to Django, which is the only layer that knows the route table
(frontend/src/App.jsx) AND the database contents:

    nginx  page requests  ->  backend: this catch-all view
    nginx  static assets  ->  frontend container (the built bundle)

* a KNOWN page route (home, shop, product detail, cart, checkout, account,
  the trust pages, ...) answers with the built ``index.html`` and status 200;
* a PRODUCT URL is only known when the slug really exists and is active --
  ``/products/does-not-exist/`` is a hard 404, exactly like the crawler
  endpoint in apps/core/seo.py;
* ``/shop/?category=<slug>`` validates the category the same way;
* anything else answers with the same document, status **404** and
  ``<meta name="robots" content="noindex">`` (plus an ``X-Robots-Tag``
  header), so a real link to a real page still renders the shop and a typo
  is a 404 for crawlers, monitoring and the back button alike.

Where the shell comes from, in order:
  1. ``SPA_INDEX_FILE`` (e.g. a copy of the built index.html on a shared
     volume) when that file exists;
  2. the repository's ``frontend/index.html`` -- the development source;
  3. ``SPA_SHELL_URL`` (default ``http://frontend/index.html`` inside the
     compose network), fetched with a short timeout and cached in-process;
  4. a small built-in Persian document, so an outage of source 3 can never
     turn every page into a blank screen.
"""
from __future__ import annotations

import json
import logging
import re
import time
from html import escape
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger("django")

#: Marker in frontend/index.html where the server injects the owner's theme.
#: It sits in <head>, BEFORE the stylesheet/JS, so the very first paint uses
#: the saved colors -- no flash of the default theme.
THEME_MARKER = "<!-- CUSIN_THEME_VARS -->"

#: ``noindex`` marker added to the 404 document. The SPA sets its own
#: per-page robots meta at runtime; this one is what a crawler sees BEFORE
#: any JavaScript runs.
NOINDEX_META = '<meta name="robots" content="noindex">'

#: Cache lifetime for the HTTP-fetched shell (the frontend container owns the
#: real file, so a deploy must be visible quickly).
SHELL_CACHE_SECONDS = 30

#: Page routes of the storefront (frontend/src/App.jsx). Keep in sync when a
#: route is added -- a missing entry turns a real page into a 404, which is
#: why the product/shop cases are checked against the database instead of
#: being listed here.
_ROUTE_PATTERNS = [
    re.compile(r"^/$"),
    re.compile(r"^/shop/?$"),
    re.compile(r"^/cart/?$"),
    re.compile(r"^/wishlist/?$"),
    re.compile(r"^/checkout/?$"),
    re.compile(r"^/payment/result(/[^/]*)?/?$"),
    re.compile(r"^/about/?$"),
    re.compile(r"^/contact/?$"),
    re.compile(r"^/shipping-returns/?$"),
    re.compile(r"^/terms/?$"),
    re.compile(r"^/privacy/?$"),
    re.compile(r"^/login/?$"),
    re.compile(r"^/register/?$"),
    re.compile(r"^/password-reset/?$"),
    re.compile(r"^/reset-password/confirm/?$"),
    re.compile(r"^/account(/[^/]+)?(/[^/]+)?/?$"),
]

_BRAND_RE = re.compile(r"^/brands/(?P<slug>[^/]+)/?$")
_PRODUCT_RE = re.compile(r"^/products/(?P<slug>[^/]+)/?$")

#: Info pages are editable rows now: their URL is only a real 200 while the
#: row exists AND is published. An unpublished/never-seeded page answers
#: exactly like any other unknown URL (404 + noindex), which is what makes
#: the storefront's own 404 view honest for crawlers too.
_INFO_PAGE_ROUTES = {
    "/about": "about",
    "/contact": "contact",
    "/shipping-returns": "shipping-returns",
    "/terms": "terms",
    "/privacy": "privacy",
}

#: Path prefixes that are NOT pages: never answered with the storefront
#: shell, whatever their content (they reach Django only by mistake -- nginx
#: serves /static/, /media/ and /api/ itself -- and a JSON/404 answer is the
#: honest one).
_NON_PAGE_PREFIXES = ("/api/", "/admin/", "/static/", "/media/", "/seo/", "/healthz")


def _query_get(query, key):
    """Value of ``key`` in a raw query string (no QueryDict needed)."""
    if not query:
        return ""
    from urllib.parse import parse_qs

    try:
        values = parse_qs(query, keep_blank_values=True, errors="replace").get(key) or []
    except (TypeError, ValueError):
        return ""
    return (values[0] or "").strip() if values else ""


def is_known_page(path, query=""):
    """
    True when ``path`` (with its query string) is a page the storefront can
    really render. Pure function of the database + the route table.
    """
    from apps.categories.models import Category
    from apps.products.models import Brand, Product

    path = path or "/"
    if any(path.startswith(prefix) for prefix in _NON_PAGE_PREFIXES):
        return False

    match = _PRODUCT_RE.match(path)
    if match:
        slug = match.group("slug")
        return Product.objects.filter(slug=slug, is_active=True).exists()

    match = _BRAND_RE.match(path)
    if match:
        return Brand.objects.filter(slug=match.group("slug"), is_active=True).exists()

    if not any(pattern.match(path) for pattern in _ROUTE_PATTERNS):
        return False

    page_slug = _INFO_PAGE_ROUTES.get(path.rstrip("/") or "/")
    if page_slug:
        from django.db import DatabaseError

        from apps.core.models import InfoPage

        try:
            return InfoPage.objects.filter(slug=page_slug, is_published=True).exists()
        except DatabaseError:  # pragma: no cover - pre-migrate deployment
            # The table does not exist yet (first deploy, before `migrate`):
            # keep the old route-table behaviour instead of 500ing the site.
            return True

    # /shop/?category=<slug> is the storefront's only query-string route: an
    # unknown category is a dead end, not an empty listing.
    if path.rstrip("/") == "/shop":
        slug = _query_get(query, "category")
        if slug and not Category.objects.filter(slug=slug, is_active=True).exists():
            return False
    return True


# --------------------------------------------------------------------------
# The SPA shell
# --------------------------------------------------------------------------

_shell_cache = {"html": "", "source": "", "at": 0.0}


def _read_index_file(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    return text if "<div id=\"root\"" in text or "<div id='root'" in text else ""


def _fetch_shell_url(url):
    import requests

    try:
        response = requests.get(url, timeout=2.5)
    except Exception as exc:  # noqa: BLE001 - a probe, never a request failure
        logger.warning("spa shell fetch failed (%s): %s", url, type(exc).__name__)
        return ""
    if response.status_code != 200:
        return ""
    # The frontend nginx may omit a charset; Requests otherwise guesses
    # ISO-8859-1 and corrupts Persian metadata in the shell.
    return response.content.decode("utf-8", errors="replace") if response.content else ""


def _configured_index_file():
    configured = getattr(settings, "SPA_INDEX_FILE", "") or ""
    if configured and Path(configured).is_file():
        return _read_index_file(configured)
    return ""


def _repository_index_file():
    """The dev source document (frontend/index.html), when it is present."""
    candidate = Path(settings.BASE_DIR).parent / "frontend" / "index.html"
    if candidate.is_file():
        return _read_index_file(candidate)
    return ""


def shell_html():
    """
    The SPA document a page request must return, or "" when nothing is
    available. Cached briefly; never raises.
    """
    now = time.monotonic()
    if _shell_cache["html"] and now - _shell_cache["at"] < SHELL_CACHE_SECONDS:
        return _shell_cache["html"]

    html = _configured_index_file()
    source = "file"
    if not html:
        html = _repository_index_file()
        source = "repo"
    if not html:
        url = getattr(settings, "SPA_SHELL_URL", "") or ""
        if url:
            html = _fetch_shell_url(url)
            source = "http"
    if html:
        _shell_cache.update({"html": html, "source": source, "at": now})
    return html


def theme_head_fragment():
    """The inline <style> + bootstrap script for the owner-selected theme.

    Read from the same cached public payload as /api/v1/site/content/, so a
    save in the admin is reflected on the next page request (the signals in
    apps/core/signals.py delete the cache entry). Never raises: a broken
    theme row must not turn every storefront page into a 500.
    """
    try:
        from .content import get_content_payload

        theme = get_content_payload().get("theme") or {}
        variables = theme.get("css_variables") or {}
    except Exception:  # noqa: BLE001 - a page must never die over a theme
        logger.warning("spa: theme variables unavailable", exc_info=True)
        return ""
    if not variables:
        return ""
    css = ":root{" + "".join(
        f"{str(name).strip()}:{str(value).strip()};" for name, value in variables.items()
    ) + "}"
    bootstrap = json.dumps(
        {
            "theme": {
                "preset": theme.get("preset", ""),
                "css_variables": variables,
                "button_radius": theme.get("button_radius", ""),
                "base_font_size": theme.get("base_font_size", ""),
                "card_shadow": theme.get("card_shadow", ""),
            }
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return (
        f'<style id="cusin-theme-vars">{css}</style>\n'
        f"<script>window.__CUSIN_THEME__={bootstrap};</script>"
    )


def _with_theme(html):
    """Inject the theme into the shell's <head> (marker or, for an older
    build without the marker, right before </head>)."""
    fragment = theme_head_fragment()
    if not fragment:
        return html
    if THEME_MARKER in html:
        return html.replace(THEME_MARKER, fragment, 1)
    index = html.lower().find("</head>")
    if index == -1:
        return fragment + html
    return f"{html[:index]}{fragment}\n{html[index:]}"


def _fallback_document(title, heading, body):
    """Built-in, dependency-free Persian document (never blank, never 200)."""
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="fa" dir="rtl">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<meta name="robots" content="noindex">',
            f"<title>{escape(title)}</title>",
            "<style>",
            "body{margin:0;background:#FAF7F0;color:#1E2412;"
            "font-family:Tahoma,system-ui,sans-serif;text-align:center;padding:12vh 6vw}",
            "h1{font-size:4rem;color:#8A6D1F;margin:0 0 8px}",
            "p{line-height:2;color:#5f6552}",
            "a{display:inline-block;margin-top:18px;background:#637037;color:#fff;"
            "padding:10px 22px;border-radius:6px;text-decoration:none}",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{escape(heading)}</h1>",
            f"<p>{escape(body)}</p>",
            '<a href="/">بازگشت به فروشگاه</a>',
            "</body>",
            "</html>",
        ]
    )


def _with_noindex(html):
    """Insert the robots meta into <head> (or prepend it when there is none)."""
    if "name=\"robots\"" in html:
        return html
    lowered = html.lower()
    for marker in ("</head>", "<body"):
        index = lowered.find(marker)
        if index != -1:
            return f"{html[:index]}{NOINDEX_META}\n{html[index:]}"
    return f"{NOINDEX_META}\n{html}"


def _page_response(html, status):
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response.status_code = status
    if status == 404:
        # The shell itself must never be cached AS a 404, and crawlers must
        # keep the URL out of the index (belt and braces next to the meta).
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Robots-Tag"] = "noindex"
    else:
        # Same rule the frontend container applied to index.html: always
        # revalidate, otherwise a customer keeps an old shell that points at
        # assets a later deploy deleted.
        response["Cache-Control"] = "no-cache, must-revalidate"
    return response


@require_GET
def spa_page(request, spa_path=""):
    """
    Catch-all for storefront page URLs. Answers with the SPA document and the
    status the URL really deserves (200 for a known page, 404 otherwise).
    """
    path = request.path
    if any(path.startswith(prefix) for prefix in _NON_PAGE_PREFIXES):
        # Not a page: /api/... or /admin/... that reached us by mistake keeps
        # Django's own 404 instead of the storefront shell.
        raise Http404("مسیر مورد نظر یک صفحهٔ فروشگاه نیست.")

    known = is_known_page(path, request.META.get("QUERY_STRING", ""))
    html = shell_html()
    if not html:
        # No shell available (frontend container down on a fresh box): still
        # a REAL Persian page with the right status.
        html = _fallback_document(
            title="صفحه یافت نشد | کازین گالری" if not known else "کازین گالری",
            heading="۴۰۴" if not known else "کازین گالری",
            body=(
                "صفحه مورد نظر پیدا نشد؛ شاید نشانی عوض شده است."
                if not known
                else "فروشگاه در حال به‌روزرسانی است؛ لطفاً چند لحظه بعد دوباره تلاش کنید."
            ),
        )
        return _page_response(html, 200 if known else 404)

    if known:
        return _page_response(_with_theme(html), 200)
    return _page_response(_with_theme(_with_noindex(html)), 404)
