from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import CartItem
from .helpers import make_product, make_user, make_variant


class UpdateCartItemTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989100000030")
        self.client.login(username="+989100000030", password="a-strong-passw0rd!")
        self.product = make_product(stock_quantity=10)
        self.item = CartItem.objects.create(cart=self._cart(), product=self.product, quantity=3)

    def _cart(self):
        from ..services import get_or_create_cart

        return get_or_create_cart(self.user)

    def _url(self, item=None):
        return reverse("cart-item-detail", args=[(item or self.item).pk])

    def test_increase_quantity(self):
        response = self.client.patch(self._url(), {"quantity": 7}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 7)

    def test_decrease_quantity(self):
        response = self.client.patch(self._url(), {"quantity": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 1)

    def test_setting_quantity_to_zero_removes_the_item(self):
        response = self.client.patch(self._url(), {"quantity": 0}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(response.data["items"], [])

    def test_negative_quantity_is_rejected(self):
        response = self.client.patch(self._url(), {"quantity": -1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)

    def test_quantity_exceeding_stock_is_rejected(self):
        response = self.client.patch(self._url(), {"quantity": 999}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)

    def test_non_integer_quantity_is_rejected(self):
        response = self.client.patch(self._url(), {"quantity": "abc"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_quantity_is_rejected(self):
        response = self.client.patch(self._url(), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_after_product_becomes_inactive_is_rejected(self):
        """Regression test for the bug found during this phase's own
        review: update_item_quantity originally only checked stock, not
        is_active, so a customer could increase the quantity of an item
        whose product had since been deactivated."""
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.client.patch(self._url(), {"quantity": 5}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)

    def test_update_after_variant_becomes_inactive_is_rejected(self):
        variant = make_variant(product=self.product, stock_quantity=10)
        variant_item = CartItem.objects.create(cart=self._cart(), product=self.product, variant=variant, quantity=2)
        variant.is_active = False
        variant.save(update_fields=["is_active"])

        response = self.client.patch(self._url(variant_item), {"quantity": 4}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        variant_item.refresh_from_db()
        self.assertEqual(variant_item.quantity, 2)

    def test_removing_an_inactive_item_is_still_allowed(self):
        """Setting quantity to 0 (removal) must work even for an
        inactive item -- only a positive-quantity update is blocked."""
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.client.patch(self._url(), {"quantity": 0}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())

    def test_decreasing_quantity_of_an_inactive_item_is_rejected(self):
        """A positive quantity change on an inactive item is blocked
        outright, even a decrease -- the item must be removed instead,
        not partially kept. This is a deliberate simplification (see
        services.update_item_quantity's docstring)."""
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.client.patch(self._url(), {"quantity": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_nonexistent_item_returns_404(self):
        response = self.client.patch(reverse("cart-item-detail", args=[999999]), {"quantity": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
