"""HTTP contract shared by every collection endpoint consumed by the SPA.

The frontend has two deliberate access patterns:

* page-at-a-time endpoints (catalog, public reviews and order history)
  expose the DRF envelope directly to their pager;
* all-items selectors (addresses, wishlist, category tree, filters, own
  reviews, banners and daily deals) follow ``next`` in
  ``frontend/src/services/pagination.js``.

Both patterns require the same four keys. Keeping this one cross-app test
near the API infrastructure prevents an endpoint from quietly changing to a
bare array while its frontend caller still assumes a collection contract.

``accounts/locations/`` and ``orders/shipping-methods/`` are intentionally
not in this list: they are singleton configuration documents (their arrays
are fields of a configuration object), not collection endpoints. There is no
customer notifications API route or frontend notification service today.
"""
from django.urls import reverse

from apps.accounts.tests.helpers import make_user
from apps.core.testing import CacheIsolatedAPITestCase
from apps.products.tests.helpers import make_product


class FrontendListEnvelopeContractTests(CacheIsolatedAPITestCase):
    """Every SPA collection GET uses DRF's count/next/previous/results shape."""

    def setUp(self):
        self.user = make_user(phone="+989199000001")
        self.product = make_product(name="قرارداد فهرست")
        self.client.force_authenticate(self.user)

    def test_every_frontend_collection_has_the_paginated_envelope(self):
        urls = {
            # Customer-owned collections.
            "addresses": reverse("address-list"),
            "orders": reverse("order-list"),
            "wishlist": reverse("wishlist"),
            "my-reviews": reverse("review-mine"),
            # Catalog and public collection surfaces.
            "products": reverse("product-list"),
            "categories": reverse("category-list"),
            "category-tree": reverse("category-tree"),
            "brands": reverse("brand-list"),
            "product-reviews": reverse("product-review-list", args=[self.product.pk]),
            "product-facets": reverse("product-facets"),
            "banners": reverse("banner-list"),
            "daily-deals": reverse("daily-deal-list"),
        }

        for name, url in urls.items():
            with self.subTest(endpoint=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertIsInstance(response.data, dict)
                for key in ("count", "next", "previous", "results"):
                    self.assertIn(key, response.data)
                self.assertIsInstance(response.data["count"], int)
                self.assertIsInstance(response.data["results"], list)
