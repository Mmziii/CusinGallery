from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import CartItem
from ..services import get_or_create_cart
from .helpers import make_product, make_user


class RemoveItemTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989100000040")
        self.client.login(username="+989100000040", password="a-strong-passw0rd!")
        self.cart = get_or_create_cart(self.user)
        self.item = CartItem.objects.create(cart=self.cart, product=make_product(), quantity=2)

    def test_remove_item(self):
        response = self.client.delete(reverse("cart-item-detail", args=[self.item.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(response.data["items"], [])

    def test_remove_nonexistent_item_returns_404(self):
        response = self.client.delete(reverse("cart-item-detail", args=[999999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_removing_one_item_leaves_others_intact(self):
        other_item = CartItem.objects.create(cart=self.cart, product=make_product(), quantity=1)
        self.client.delete(reverse("cart-item-detail", args=[self.item.pk]))
        self.assertTrue(CartItem.objects.filter(pk=other_item.pk).exists())


class ClearCartTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989100000041")
        self.client.login(username="+989100000041", password="a-strong-passw0rd!")
        self.cart = get_or_create_cart(self.user)

    def test_clear_cart_with_items(self):
        CartItem.objects.create(cart=self.cart, product=make_product(), quantity=1)
        CartItem.objects.create(cart=self.cart, product=make_product(), quantity=2)

        response = self.client.delete(reverse("cart"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["item_count"], 0)
        self.assertEqual(response.data["subtotal"], 0)
        self.assertEqual(CartItem.objects.filter(cart=self.cart).count(), 0)

    def test_clear_cart_keeps_the_cart_row_itself(self):
        """Clearing empties the items, not the Cart row -- the OneToOne
        Cart<->User relationship (Phase 2) should still resolve to the
        same cart afterward, not require re-creation."""
        CartItem.objects.create(cart=self.cart, product=make_product(), quantity=1)
        self.client.delete(reverse("cart"))

        from ..models import Cart

        self.assertTrue(Cart.objects.filter(pk=self.cart.pk).exists())

    def test_clear_already_empty_cart_does_not_error(self):
        response = self.client.delete(reverse("cart"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])


class EmptyCartTests(APITestCase):
    def test_get_cart_before_any_item_added_returns_empty_shape(self):
        make_user(phone="+989100000042")
        self.client.login(username="+989100000042", password="a-strong-passw0rd!")

        response = self.client.get(reverse("cart"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["item_count"], 0)
        self.assertEqual(response.data["subtotal"], 0)
        self.assertEqual(response.data["total"], 0)
        self.assertIn("id", response.data)
