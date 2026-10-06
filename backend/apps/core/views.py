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
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import SiteSettingsSerializer

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


class SiteSettingsView(APIView):
    """Public read-only view of the store's contact/branding settings
    (Part 1): footer, contact page, pickup info and the floating contact
    button all read this one endpoint instead of hardcoding business
    content in the bundle."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .models import SiteSettings

        return Response(SiteSettingsSerializer(SiteSettings.load()).data)


class ReportFrontendErrorView(APIView):
    """
    Part S3 item 9: capture endpoint for storefront error reports.

    The frontend ships WITHOUT a Sentry SDK (no heavy dependency); when
    VITE_SENTRY_DSN is set at build time the ErrorBoundary/window error
    handler POSTs a short report here, and THIS view forwards it into the
    existing backend Sentry setup (settings.SENTRY_DSN + sentry_sdk).
    Both gates must be open for data to leave the browser: no frontend
    env var = the browser never sends; no backend DSN = the report is
    only written to the server log.

    AllowAny + strict size caps + a dedicated throttle scope: an error
    reporter must work for logged-out visitors (crashes are not
    authenticated) but must not be usable as a free spam/log-flood pipe.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "error_report"

    def post(self, request):
        message = str(request.data.get("message") or "")[:2000].strip()
        if not message:
            return Response({"message": ["پیام خطا الزامی است."]}, status=400)
        component = str(request.data.get("component") or "")[:200]
        page_url = str(request.data.get("url") or "")[:500]
        stack = str(request.data.get("stack") or "")[:8000]

        forwarded = False
        if getattr(settings, "SENTRY_DSN", ""):
            try:
                import sentry_sdk

                sentry_sdk.set_context(
                    "frontend_report",
                    {
                        "component": component,
                        "url": page_url,
                        "stack": stack,
                    },
                )
                sentry_sdk.capture_message(f"[frontend] {message}", level="error")
                forwarded = True
            except Exception:  # noqa: BLE001 - reporting must never crash
                logger.exception("frontend error report could not reach Sentry")

        # Always keep a server-side trace too (works with no Sentry at all).
        logger.warning(
            "frontend error report: %s | component=%s url=%s",
            message,
            component or "-",
            page_url or "-",
        )
        return Response({"detail": "گزارش دریافت شد.", "forwarded": forwarded}, status=202)
