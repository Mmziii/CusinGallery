"""
Site-level infrastructure views (Phase E - Production readiness & SEO).

Three tiny endpoints mounted at the site ROOT by config/urls.py (and
proxied to the backend by the nginx configs):

    GET /healthz      liveness/readiness probe for monitoring: always
                      answers fast; includes a real database round-trip
                      and returns 503 when the DB is unreachable, so an
                      uptime monitor sees actual unavailability instead
                      of a green checkmark on a half-broken app.
                      Unauthenticated by design (no secrets in output).

    GET /robots.txt   crawler policy: everything public is allowed,
                      /admin/ and /api/ are disallowed, and the sitemap
                      location is advertised.

    GET /sitemap.xml  product URLs + the storefront's static/trust
                      pages, built on FRONTEND_URL (the canonical public
                      origin). Persian slugs are percent-encoded per
                      RFC 3986 (iri_to_uri), which is exactly what the
                      sitemap protocol requires for non-ASCII URLs.
                      Categories deliberately get no <url> entries: the
                      storefront has no standalone category pages (the
                      shop page filters by query string), and sitemaps
                      should only list canonical, indexable pages.

Honest SEO note: this is a client-rendered SPA, so per-product Open
Graph tags cannot be seen by social crawlers that don't execute JS --
the frontend sets document titles/meta/canonicals at runtime (good for
Google, which renders JS) and index.html carries the site-wide OG
defaults. Server-rendered per-product OG/prerendering is a documented
future improvement, not something silently half-done here.
"""
import logging
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.utils.encoding import iri_to_uri

logger = logging.getLogger("django")

#: Static storefront pages (routes in frontend/src/App.jsx) with their
#: sitemap priorities/change frequencies. Kept here (backend) because the
#: sitemap is served by Django; if a route is renamed, update both.
STATIC_SITEMAP_PAGES = [
    ("", "1.0", "daily"),            # home
    ("/shop/", "0.9", "daily"),      # catalog
    ("/about/", "0.3", "yearly"),
    ("/contact/", "0.3", "yearly"),
    ("/shipping-returns/", "0.3", "monthly"),
    ("/terms/", "0.3", "yearly"),
    ("/privacy/", "0.3", "yearly"),
]


def healthz(request):
    """Monitoring probe: 200 {"status": "ok"} when the process AND the
    database answer; 503 {"status": "degraded"} with the failure class
    (never details) when the DB round-trip fails."""
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception as exc:
        db_ok = False
        logger.error("healthz: database unreachable: %s", type(exc).__name__)
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
    }
    return JsonResponse(body, status=200 if db_ok else 503)


def robots_txt(request):
    base = settings.FRONTEND_URL.rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /api/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    from apps.products.models import Product

    base = settings.FRONTEND_URL.rstrip("/")
    urls = []
    for path, priority, changefreq in STATIC_SITEMAP_PAGES:
        urls.append((f"{base}/{path.lstrip('/')}", None, changefreq, priority))
    for product in (
        Product.objects.filter(is_active=True)
        .only("slug", "updated_at")
        .order_by("-updated_at")[:20000]  # single-file sitemap well under the 50k URL cap
    ):
        urls.append((
            f"{base}/products/{product.slug}/",
            product.updated_at,
            "weekly",
            "0.8",
        ))

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, changefreq, priority in urls:
        parts.append("  <url>")
        # iri_to_uri percent-encodes non-ASCII (Persian) slugs exactly as
        # the sitemap protocol requires; escape() keeps the XML valid.
        parts.append(f"    <loc>{escape(iri_to_uri(loc))}</loc>")
        if lastmod is not None:
            parts.append(f"    <lastmod>{lastmod:%Y-%m-%d}</lastmod>")
        parts.append(f"    <changefreq>{changefreq}</changefreq>")
        parts.append(f"    <priority>{priority}</priority>")
        parts.append("  </url>")
    parts.append("</urlset>")
    return HttpResponse("\n".join(parts), content_type="application/xml; charset=utf-8")
