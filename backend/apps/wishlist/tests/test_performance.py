"""
N+1 regression test for the wishlist list endpoint -- same
"compare across sizes, not a pinned literal" methodology as
apps/cart/tests/test_performance.py and apps/products/tests/test_performance.py.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import WishlistItem
from .helpers import make_product, make_user


def _query_count_for(client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
        assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


class WishlistQueryCountTests(CacheIsolatedAPITestCase):
    def test_list_query_count_does_not_scale_with_item_count(self):
        user = make_user(phone="+989200000010")
        self.client.login(username="+989200000010", password="a-strong-passw0rd!")

        for _ in range(3):
            WishlistItem.objects.create(user=user, product=make_product())
        small_count = _query_count_for(self.client, reverse("wishlist"))

        for _ in range(12):  # 15 total
            WishlistItem.objects.create(user=user, product=make_product())
        large_count = _query_count_for(self.client, reverse("wishlist"))

        self.assertEqual(
            small_count,
            large_count,
            f"Wishlist GET query count grew with item count ({small_count} -> {large_count}) -- "
            f"likely an N+1 in _wishlist_queryset or WishlistItemSerializer.",
        )
