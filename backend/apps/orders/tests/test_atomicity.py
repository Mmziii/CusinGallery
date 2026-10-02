"""
Transaction/atomicity tests.

True concurrent-thread testing is notoriously hard to do reliably inside
Django's transaction-wrapped TestCase machinery (each test runs inside a
transaction that's rolled back at the end, and genuine concurrency needs
separate DB connections/threads coordinated around that) -- building that
harness would be disproportionate complexity for what this phase needs
to demonstrate. What's tested here instead is deterministic and
realistic without needing real threads:
    - that a rejected checkout leaves no partial Order/OrderItem/cleared
      cart behind (the actual failure mode a race or a mid-transaction
      error would produce, if the atomic block didn't work)
    - that services.checkout's locking call
      (`cart.items.select_for_update()`) is present and doesn't itself
      break normal sequential checkout behavior
    - that two sequential checkouts of the same cart behave correctly
      (the second sees an empty cart, matching what the lock is meant to
      guarantee happens under real concurrency too)
"""
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ...cart.models import Cart, CartItem
from ..models import Order, OrderItem
from ..services import checkout
from .helpers import add_to_cart, make_product, make_user, valid_checkout_payload


class FailedCheckoutLeavesNoPartialStateTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989302000001")
        self.client.login(username="+989302000001", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def test_rejected_checkout_creates_no_order_or_items(self):
        available = make_product(name="OK", stock_quantity=5)
        unavailable = make_product(name="Not OK", is_active=False)
        add_to_cart(self.user, available, quantity=1)
        add_to_cart(self.user, unavailable, quantity=1)

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_exception_mid_checkout_rolls_back_the_whole_transaction(self):
        """Simulates a failure partway through order-item creation (e.g.
        an unexpected DB error) and confirms transaction.atomic() rolled
        back the Order that had already been created, and left the cart
        untouched -- not a half-created order with no items, and not a
        cleared cart with no resulting order."""
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        with patch("apps.orders.services.OrderItem.objects.bulk_create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                checkout(self.user, valid_checkout_payload())

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 1)


class SequentialCheckoutTests(APITestCase):
    """What the select_for_update() lock is meant to guarantee under
    real concurrency -- verified here in its simpler, deterministic
    sequential form: after checkout, the same cart is empty, so a
    second immediate checkout attempt correctly sees nothing to order."""

    def setUp(self):
        self.user = make_user(phone="+989302000002")
        self.client.login(username="+989302000002", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def test_second_checkout_of_the_same_now_empty_cart_is_rejected(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        first = self.client.post(self.url, valid_checkout_payload(), format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(self.url, valid_checkout_payload(), format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cart", second.data)

        # Exactly one order exists -- the second attempt did not create
        # a duplicate or an empty order.
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)

    def test_checkout_does_not_create_a_second_cart_row(self):
        """Cart is OneToOneField(User) (Phase 2) -- checkout must reuse
        the existing cart, never create a second one for the same user."""
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(Cart.objects.filter(user=self.user).count(), 1)

    def test_checkout_service_locks_cart_items_for_update(self):
        """Confirms the actual locking call is present in the checkout
        path -- a regression guard against someone later 'simplifying'
        services.checkout and silently dropping the lock that protects
        against the double-submit race this test class is about."""
        import inspect

        from .. import services

        source = inspect.getsource(services.checkout)
        self.assertIn("select_for_update", source)
