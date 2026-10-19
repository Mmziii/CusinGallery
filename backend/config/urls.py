"""
Root URL configuration.

Per-app API routes live under apps/<app>/urls.py and are aggregated in
config/api_urls.py, mounted at /api/v1/. Each app's urls.py currently
exposes an empty urlpatterns list -- endpoints are added as each app's
phase is implemented (see README.md for the phase plan).

Part R3: the admin panel path is configurable through the ADMIN_URL
environment variable (default "admin/"). Set a hard-to-guess value in
production (e.g. ADMIN_URL=panel-cusin-88) -- check_production warns
while it stays the default. Always restart the backend after changing it.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from apps.adminui.views import quick_search
from apps.analytics.admin_views import (
    reports_export,
    reports_print,
    reports_view,
)
from apps.core.seo import brand_meta, product_meta, shop_meta
from apps.core.spa import spa_page
from apps.core.views import healthz, robots_txt, sitemap_xml

# settings.ADMIN_PATH is the single source of truth (also used by
# apps.core.middleware.AdminFrameOptionsMiddleware for the SAMEORIGIN
# exception); mount it without the leading slash.
_admin_path = settings.ADMIN_PATH.lstrip("/")

# Part R4 item 4: admin two-factor gate -- swaps the admin site class to
# django-otp's OTPAdminSite when ADMIN_2FA_REQUIRED is on (no-op in dev
# and tests, where the flag defaults off). Must run before admin.urls.
from apps.core.admin_2fa import configure_admin_2fa  # noqa: E402

configure_admin_2fa()

urlpatterns = [
    # Staff-only quick-search JSON for the admin palette (B6). Mounted
    # inside the admin prefix BEFORE admin.site.urls: its hyphenated
    # segment can never collide with the admin's (\w+) app/model routes,
    # and it inherits the admin's robots/X-Frame posture by living here.
    path(
        f"{_admin_path}quick-search/",
        quick_search,
        name="admin_quick_search",
    ),
    # «گزارش‌ها و تحلیل» (analytics): the report page, its exports and
    # the print view all live under the admin prefix and enforce their
    # own staff/permission checks (apps/analytics/admin_views.py).
    path(f"{_admin_path}reports/", reports_view, name="admin_reports"),
    path(f"{_admin_path}reports/export/", reports_export, name="admin_reports_export"),
    path(f"{_admin_path}reports/print/", reports_print, name="admin_reports_print"),
    path(_admin_path, admin.site.urls),
    path("api/v1/", include("config.api_urls")),
    # Site-level infrastructure (Phase E): monitoring probe + SEO files.
    # Served at the public root; the nginx configs proxy /healthz,
    # /robots.txt and /sitemap.xml here.
    path("healthz", healthz, name="healthz"),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap-xml"),
    # Part S4 item 3: crawler-visible meta. The nginx configs route known
    # bot user agents for /products/<slug>/ and /shop/?category=<slug> to
    # these two endpoints (a real shopper keeps getting the SPA); they are
    # plain, minimal HTML documents, not part of the public API.
    path("seo/product/<str:slug>/", product_meta, name="seo-product"),
    path("seo/shop/", shop_meta, name="seo-shop"),
    path("seo/brand/<str:slug>/", brand_meta, name="seo-brand"),
    # Alias of apps.payments' callback endpoint at the site root, matching
    # the PAYMENT_CALLBACK_URL shape documented in .env.example
    # (https://cusin.ir/payment/callback/). Same view either way -- see
    # apps/payments/urls_root.py.
    path("", include("apps.payments.urls_root")),
]

# Serve uploaded media locally in development only. In production, Nginx
# serves /media/ directly (see nginx/conf.d/cusin.conf) -- Django/Gunicorn
# never serves media files in production.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ---------------------------------------------------------------------------
# Storefront catch-all (Audit 19 item 5) -- MUST stay last.
# ---------------------------------------------------------------------------
# nginx routes page requests here instead of answering every path with the
# SPA shell, so /nonexistent-xyz and /products/does-not-exist/ are real 404s
# (with the same Persian 404 page) instead of "200 with the 404 design".
# It is appended AFTER the DEBUG media route above so /media/ keeps working
# in development; anything that is not a page (/api/, /admin/, /static/,
# /media/, /seo/, /healthz) is rejected with Django's own 404.
urlpatterns += [
    re_path(r"^(?P<spa_path>.*)$", spa_page, name="spa-page"),
]
