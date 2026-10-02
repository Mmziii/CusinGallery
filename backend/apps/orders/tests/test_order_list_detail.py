from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Order
from .helpers import make_user, valid_checkout_payload
from .helpers import add_to_cart, make_product


def _checkout(client, user, username, product=None):
    client.login(username=username, password="a-strong-passw0rd!")
    product = product or make_product(stock_quantity=5)
    add_to_cart(user, product, quantity=1)
    response = client.post(reverse("checkout"), valid_checkout_payload(), format="json")
    assert response.status_code == status.HTTP_201_CREATED, response.data
    client.logout()
    return response.data["id"]


class OrderListOwnershipTests(APITestCase):
    def test_anonymous_cannot_list_orders(self):
        response = self.client.get(reverse("order-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_only_sees_their_own_orders(self):
        owner = make_user(phone="+989301000001")
        intruder = make_user(phone="+989301000002")
        _checkout(self.client, owner, "+989301000001")

        self.client.login(username="+989301000002", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_list_is_paginated(self):
        user = make_user(phone="+989301000003")
        for _ in range(3):
            _checkout(self.client, user, "+989301000003")

        self.client.login(username="+989301000003", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-list"))
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)
        self.assertEqual(response.data["count"], 3)

    def test_list_orders_newest_first(self):
        user = make_user(phone="+989301000004")
        first_id = _checkout(self.client, user, "+989301000004")
        second_id = _checkout(self.client, user, "+989301000004")

        self.client.login(username="+989301000004", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-list"))
        ids = [o["id"] for o in response.data["results"]]
        self.assertEqual(ids, [second_id, first_id])


class OrderDetailOwnershipTests(APITestCase):
    def test_anonymous_cannot_view_order_detail(self):
        owner = make_user(phone="+989301000005")
        order_id = _checkout(self.client, owner, "+989301000005")
        response = self.client.get(reverse("order-detail", args=[order_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_view_their_own_order(self):
        owner = make_user(phone="+989301000006")
        order_id = _checkout(self.client, owner, "+989301000006")

        self.client.login(username="+989301000006", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-detail", args=[order_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], order_id)

    def test_user_cannot_view_another_users_order_by_guessing_id(self):
        """The critical security case: changing the ID in the URL must
        not leak another user's order -- it must 404, not 403 (doesn't
        even appear to exist from the intruder's point of view), and
        must not leak any of its contents in the response body."""
        owner = make_user(phone="+989301000007")
        intruder = make_user(phone="+989301000008")
        order_id = _checkout(self.client, owner, "+989301000007")

        self.client.login(username="+989301000008", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-detail", args=[order_id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("order_number", str(response.data))

    def test_nonexistent_order_returns_404(self):
        make_user(phone="+989301000009")
        self.client.login(username="+989301000009", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-detail", args=[999999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_detail_includes_full_item_and_shipping_data(self):
        owner = make_user(phone="+989301000010")
        order_id = _checkout(self.client, owner, "+989301000010")

        self.client.login(username="+989301000010", password="a-strong-passw0rd!")
        response = self.client.get(reverse("order-detail", args=[order_id]))

        self.assertIn("items", response.data)
        self.assertIn("shipping_recipient_name", response.data)
        self.assertIn("order_number", response.data)
