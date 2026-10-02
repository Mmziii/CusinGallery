"""
N+1 regression tests -- same "compare query counts across different
sizes, don't pin a fragile literal number" methodology established in
Phase 4/5's test suites.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import add_to_cart, make_product, make_user, valid_checkout_payload


def _query_count_for(client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
        assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


def _place_order(client, user, product_count=1):
    for _ in range(product_count):
        add_to_cart(user, make_product(stock_quantity=5), quantity=1)
    response = client.post(reverse("checkout"), valid_checkout_payload(), format="json")
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return response.data["id"]


class OrderListQueryCountTests(APITestCase):
    def test_list_query_count_does_not_scale_with_order_count(self):
        user = make_user(phone="+989303000001")
        self.client.login(username="+989303000001", password="a-strong-passw0rd!")

        for _ in range(3):
            _place_order(self.client, user, product_count=2)
        small_count = _query_count_for(self.client, reverse("order-list"))

        for _ in range(9):  # 12 orders total
            _place_order(self.client, user, product_count=2)
        large_count = _query_count_for(self.client, reverse("order-list"))

        self.assertEqual(
            small_count,
            large_count,
            f"Order list query count grew with order count ({small_count} -> {large_count}) -- "
            f"likely an N+1 in _order_queryset or OrderSerializer.",
        )

    def test_list_query_count_does_not_scale_with_items_per_order(self):
        """Specifically targets the items prefetch -- an order with many
        line items must not cost proportionally more queries."""
        user = make_user(phone="+989303000002")
        self.client.login(username="+989303000002", password="a-strong-passw0rd!")

        _place_order(self.client, user, product_count=2)
        small_count = _query_count_for(self.client, reverse("order-list"))

        _place_order(self.client, user, product_count=10)
        large_count = _query_count_for(self.client, reverse("order-list"))

        self.assertEqual(small_count, large_count)


class OrderDetailQueryCountTests(APITestCase):
    def test_detail_query_count_does_not_scale_with_item_count(self):
        user = make_user(phone="+989303000003")
        self.client.login(username="+989303000003", password="a-strong-passw0rd!")

        order_id = _place_order(self.client, user, product_count=2)
        small_count = _query_count_for(self.client, reverse("order-detail", args=[order_id]))

        order_id_large = _place_order(self.client, user, product_count=10)
        large_count = _query_count_for(self.client, reverse("order-detail", args=[order_id_large]))

        self.assertEqual(small_count, large_count)


class CheckoutQueryCountTests(APITestCase):
    """The checkout endpoint itself processes every cart line -- the
    most important place to confirm query count doesn't scale with cart
    size, since a customer with a large cart shouldn't cost the server
    proportionally more work to check out."""

    def _checkout_query_count(self, client, user, product_count):
        for _ in range(product_count):
            add_to_cart(user, make_product(stock_quantity=5), quantity=1)
        with CaptureQueriesContext(connection) as ctx:
            response = client.post(reverse("checkout"), valid_checkout_payload(), format="json")
            assert response.status_code == status.HTTP_201_CREATED, response.data
        return len(ctx.captured_queries)

    def test_checkout_query_count_does_not_scale_with_cart_size(self):
        small_user = make_user(phone="+989303000004")
        self.client.login(username="+989303000004", password="a-strong-passw0rd!")
        small_count = self._checkout_query_count(self.client, small_user, product_count=2)
        self.client.logout()

        large_user = make_user(phone="+989303000005")
        self.client.login(username="+989303000005", password="a-strong-passw0rd!")
        large_count = self._checkout_query_count(self.client, large_user, product_count=15)

        self.assertEqual(
            small_count,
            large_count,
            f"Checkout query count grew with cart size ({small_count} -> {large_count}) -- "
            f"likely an N+1 in services.checkout (e.g. a per-item save() instead of bulk_create).",
        )
