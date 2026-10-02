"""
N+1 regression tests.

Deliberately compare query counts ACROSS different numbers of products
rather than asserting one fixed literal number -- a fixed number is
fragile (any unrelated middleware/auth query would break it) and, more
importantly, isn't actually what matters: what must be true is that the
query count stays CONSTANT as the amount of data grows, not that it
equals some specific value. That's the actual definition of "no N+1".
"""
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from rest_framework.test import APITestCase

from .helpers import make_brand, make_category, make_image, make_product, make_variant


def _query_count_for(client, url, params=None):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url, params or {})
        assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


class ProductListQueryCountTests(APITestCase):
    def test_list_query_count_does_not_scale_with_product_count(self):
        category = make_category()
        brand = make_brand()

        def make_n_products(n):
            for i in range(n):
                p = make_product(category=category, brand=brand, name=f"Product {i}")
                make_image(p, is_primary=True)

        make_n_products(3)
        small_count = _query_count_for(self.client, reverse("product-list"))

        make_n_products(12)  # now 15 total, still under PAGE_SIZE=20
        large_count = _query_count_for(self.client, reverse("product-list"))

        self.assertEqual(
            small_count,
            large_count,
            f"Query count grew with product count ({small_count} -> {large_count}) -- "
            f"likely an N+1 in ProductViewSet.get_queryset or ProductListSerializer.",
        )

    def test_list_with_multiple_images_per_product_does_not_scale(self):
        """Specifically targets get_primary_image -- must read from the
        prefetch cache, not issue a fresh query per product."""
        category = make_category()

        def make_products_with_images(n, images_each):
            for i in range(n):
                p = make_product(category=category, name=f"Multi {i}")
                for j in range(images_each):
                    make_image(p, is_primary=(j == 0))

        make_products_with_images(2, 3)
        small_count = _query_count_for(self.client, reverse("product-list"))

        make_products_with_images(8, 3)  # 10 products total, 3 images each
        large_count = _query_count_for(self.client, reverse("product-list"))

        self.assertEqual(small_count, large_count)


class ProductDetailQueryCountTests(APITestCase):
    def test_related_products_query_is_bounded_not_per_related_item(self):
        category = make_category()
        main = make_product(category=category, name="Main", slug="qc-main")
        for i in range(3):
            make_product(category=category, name=f"Sibling {i}", slug=f"qc-sibling-{i}")
        small_count = _query_count_for(self.client, reverse("product-detail", args=["qc-main"]))

        for i in range(3, 15):
            make_product(category=category, name=f"Sibling {i}", slug=f"qc-sibling-{i}")
        large_count = _query_count_for(self.client, reverse("product-detail", args=["qc-main"]))

        self.assertEqual(
            small_count,
            large_count,
            "Detail view's query count grew with the number of same-category "
            "products -- likely an N+1 in get_related_products.",
        )

    def test_variants_and_specifications_query_count_does_not_scale_with_variant_count(self):
        product = make_product(name="Many Variants", slug="qc-many-variants")
        for i in range(2):
            make_variant(product, sku=f"QC-VAR-{i}")
        small_count = _query_count_for(self.client, reverse("product-detail", args=["qc-many-variants"]))

        for i in range(2, 12):
            make_variant(product, sku=f"QC-VAR-{i}")
        large_count = _query_count_for(self.client, reverse("product-detail", args=["qc-many-variants"]))

        self.assertEqual(
            small_count,
            large_count,
            "Detail view's query count grew with the number of variants -- "
            "likely an N+1 in get_variants or get_specifications.",
        )
