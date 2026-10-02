"""
Root URL configuration.

Per-app API routes live under apps/<app>/urls.py and are aggregated in
config/api_urls.py, mounted at /api/v1/. Each app's urls.py currently
exposes an empty urlpatterns list -- endpoints are added as each app's
phase is implemented (see README.md for the phase plan).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("config.api_urls")),
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
