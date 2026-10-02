"""
N+1 regression tests -- compares query counts across different cart
sizes rather than pinning one fragile literal number, same methodology
as apps/products/tests/test_performance.py (Phase 4): what matters is
that the count doesn't scale with the number of items, not that it
equals some specific value.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import CartItem
from ..services import get_or_create_cart
from .helpers import make_product, make_user, make_variant


def _query_count_for(client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
        assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


class CartQueryCountTests(CacheIsolatedAPITestCase):
    def test_get_cart_query_count_does_not_scale_with_item_count(self):
        user = make_user(phone="+989100000060")
        self.client.login(username="+989100000060", password="a-strong-passw0rd!")
        cart = get_or_create_cart(user)

        for _ in range(3):
            CartItem.objects.create(cart=cart, product=make_product(stock_quantity=10), quantity=1)
        small_count = _query_count_for(self.client, reverse("cart"))

        for _ in range(12):  # 15 total items
            CartItem.objects.create(cart=cart, product=make_product(stock_quantity=10), quantity=1)
        large_count = _query_count_for(self.client, reverse("cart"))

        self.assertEqual(
            small_count,
            large_count,
            f"Cart GET query count grew with item count ({small_count} -> {large_count}) -- "
            f"likely an N+1 in cart.services.build_cart_view.",
        )

    def test_get_cart_with_variants_and_attributes_does_not_scale(self):
        user = make_user(phone="+989100000061")
        self.client.login(username="+989100000061", password="a-strong-passw0rd!")
        cart = get_or_create_cart(user)

        def add_variant_items(n):
            for _ in range(n):
                product = make_product(stock_quantity=10)
                variant = make_variant(product=product, stock_quantity=10)
                CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)

        add_variant_items(2)
        small_count = _query_count_for(self.client, reverse("cart"))

        add_variant_items(10)
        large_count = _query_count_for(self.client, reverse("cart"))

        self.assertEqual(small_count, large_count)
