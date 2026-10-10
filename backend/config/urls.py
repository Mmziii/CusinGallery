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
import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.seo import product_meta, shop_meta
from apps.core.views import healthz, robots_txt, sitemap_xml

_admin_path = os.environ.get("ADMIN_URL", "admin/").strip()
_admin_path = (_admin_path.strip("/") + "/") if _admin_path.strip("/") else "admin/"

# Part R4 item 4: admin two-factor gate -- swaps the admin site class to
# django-otp's OTPAdminSite when ADMIN_2FA_REQUIRED is on (no-op in dev
# and tests, where the flag defaults off). Must run before admin.urls.
from apps.core.admin_2fa import configure_admin_2fa  # noqa: E402

configure_admin_2fa()

urlpatterns = [
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
