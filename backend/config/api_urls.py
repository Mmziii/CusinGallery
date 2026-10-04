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
    # Public store contact/branding settings (Part 1): footer, contact
    # page, pickup info, floating contact button.
    path("site/settings/", apps_core_views.SiteSettingsView.as_view(), name="site-settings"),
]
