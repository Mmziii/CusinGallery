"""
Aggregates every app's API routes under a single /api/v1/ namespace.

`accounts/` has real endpoints as of Phase 3 (registration, login,
profile, addresses, ...). `products/` and `categories/` have real
endpoints as of Phase 4. `cart/` and `wishlist/` have real endpoints as
of Phase 5. `orders/` has real endpoints as of Phase 6 (checkout, order
list/detail). Every other include() below still points at an app whose
urls.py currently defines an empty urlpatterns list -- nothing 404s in a
confusing way, those paths simply have no endpoints registered yet, and
each app fills in its own urls.py as its phase is implemented.

`brands/` is the one deliberate exception to "one path per app": Brand
is still modeled inside apps.products (Phase 2 didn't create a separate
"brands" app, and Phase 4 doesn't either, per the instruction not to
restructure existing apps unnecessarily) but is exposed at this
top-level path -- matching the flat convention the master spec's API
section suggests -- via apps/products/urls_brands.py, a second, small
urls module in that same app.
"""
from django.urls import include, path

from apps.core import views as apps_core_views

urlpatterns = [
    path("accounts/", include("apps.accounts.urls")),
    path("products/", include("apps.products.urls")),
    path("brands/", include("apps.products.urls_brands")),
    path("categories/", include("apps.categories.urls")),
    path("cart/", include("apps.cart.urls")),
    path("wishlist/", include("apps.wishlist.urls")),
    path("discounts/", include("apps.discounts.urls")),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("banners/", include("apps.banners.urls")),
    # Batched, fire-and-forget storefront behaviour events (privacy-friendly:
    # no IP, no user agent -- see apps/analytics/models.py).
    path("analytics/", include("apps.analytics.urls")),
    # Public store contact/branding settings (Part 1): footer, contact
    # page, pickup info, floating contact button.
    path("site/settings/", apps_core_views.SiteSettingsView.as_view(), name="site-settings"),
    # Owner-editable content + theme (cached; invalidated on save). This is
    # the ONE endpoint the storefront reads for brand/home/trust/footer/
    # floating text and the CSS variables of the selected theme.
    path("site/content/", apps_core_views.SiteContentView.as_view(), name="site-content"),
    # The five info pages. Unpublished pages answer 404 (same as their URL),
    # so the storefront can render its real not-found view.
    path(
        "site/pages/<slug:slug>/",
        apps_core_views.InfoPageView.as_view(),
        name="site-info-page",
    ),
    # Part S3 item 9: storefront error reports land here and are forwarded
    # to the existing Sentry setup (only when SENTRY_DSN is configured).
    path(
        "site/report-error/",
        apps_core_views.ReportFrontendErrorView.as_view(),
        name="site-report-error",
    ),
]
