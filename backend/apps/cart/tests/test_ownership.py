from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import Cart, CartItem
from .helpers import make_product, make_user


class CartOwnershipTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.owner = make_user(phone="+989100000010")
        self.intruder = make_user(phone="+989100000011")
        self.product = make_product()
        self.owner_cart = Cart.objects.create(user=self.owner)
        self.owner_item = CartItem.objects.create(cart=self.owner_cart, product=self.product, quantity=2)

    def test_user_cannot_see_another_users_cart_contents(self):
        """There is no cart-id parameter anywhere in the API -- GET
        /cart/ always resolves the cart from request.user server-side,
        so there's no way to even attempt to view someone else's cart by
        ID. This test confirms the intruder's OWN (empty) cart is what
        they see, not the owner's."""
        self.client.login(username="+989100000011", password="a-strong-passw0rd!")
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])

    def test_user_cannot_update_another_users_cart_item(self):
        self.client.login(username="+989100000011", password="a-strong-passw0rd!")
        detail_url = reverse("cart-item-detail", args=[self.owner_item.pk])
        response = self.client.patch(detail_url, {"quantity": 5}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.owner_item.refresh_from_db()
        self.assertEqual(self.owner_item.quantity, 2)

    def test_user_cannot_delete_another_users_cart_item(self):
        self.client.login(username="+989100000011", password="a-strong-passw0rd!")
        detail_url = reverse("cart-item-detail", args=[self.owner_item.pk])
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(CartItem.objects.filter(pk=self.owner_item.pk).exists())

    def test_clearing_own_cart_does_not_affect_another_users_cart(self):
        self.client.login(username="+989100000011", password="a-strong-passw0rd!")
        self.client.delete(reverse("cart"))
        self.assertTrue(CartItem.objects.filter(pk=self.owner_item.pk).exists())

    def test_adding_item_never_creates_a_second_cart_for_the_same_user(self):
        """GET /cart/ auto-creates a Cart if missing -- confirms a
        second call (e.g. from adding an item) reuses it via the
        OneToOne constraint (Phase 2), not a duplicate."""
        self.client.login(username="+989100000010", password="a-strong-passw0rd!")
        self.client.get(reverse("cart"))
        self.client.get(reverse("cart"))
        self.assertEqual(Cart.objects.filter(user=self.owner).count(), 1)
