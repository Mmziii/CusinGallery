from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import CartItem
from .helpers import make_product, make_user, make_variant


class AddCartItemTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989100000020")
        self.client.login(username="+989100000020", password="a-strong-passw0rd!")
        self.url = reverse("cart-item-create")

    def test_add_simple_product(self):
        product = make_product(price=150000, stock_quantity=5)
        response = self.client.post(self.url, {"product_id": product.id, "quantity": 2}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["items"]), 1)
        line = response.data["items"][0]
        self.assertEqual(line["quantity"], 2)
        self.assertEqual(line["product"]["id"], product.id)
        self.assertIsNone(line["variant"])
        self.assertEqual(line["price_info"]["price"], 150000)
        self.assertEqual(line["line_total"], 300000)

    def test_add_product_variant(self):
        product = make_product(price=100000)
        variant = make_variant(product=product, price=120000, stock_quantity=5)
        response = self.client.post(
            self.url, {"product_id": product.id, "variant_id": variant.id, "quantity": 1}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        line = response.data["items"][0]
        self.assertEqual(line["variant"]["id"], variant.id)
        self.assertEqual(line["price_info"]["price"], 120000)

    def test_adding_same_product_twice_increments_not_duplicates(self):
        product = make_product(stock_quantity=10)
        self.client.post(self.url, {"product_id": product.id, "quantity": 2}, format="json")
        response = self.client.post(self.url, {"product_id": product.id, "quantity": 3}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["quantity"], 5)
        self.assertEqual(CartItem.objects.filter(product=product).count(), 1)

    def test_adding_same_variant_twice_increments_not_duplicates(self):
        product = make_product()
        variant = make_variant(product=product, stock_quantity=10)
        self.client.post(
            self.url, {"product_id": product.id, "variant_id": variant.id, "quantity": 1}, format="json"
        )
        response = self.client.post(
            self.url, {"product_id": product.id, "variant_id": variant.id, "quantity": 2}, format="json"
        )

        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["quantity"], 3)
        self.assertEqual(CartItem.objects.filter(product=product, variant=variant).count(), 1)

    def test_same_product_different_variants_are_separate_lines(self):
        product = make_product()
        red = make_variant(product=product, sku="RED", stock_quantity=5)
        blue = make_variant(product=product, sku="BLUE", stock_quantity=5)
        self.client.post(self.url, {"product_id": product.id, "variant_id": red.id, "quantity": 1}, format="json")
        response = self.client.post(
            self.url, {"product_id": product.id, "variant_id": blue.id, "quantity": 1}, format="json"
        )
        self.assertEqual(len(response.data["items"]), 2)

    def test_product_with_variant_and_without_are_separate_lines(self):
        """Regression guard for the exact Phase 2 constraint shape: one
        (cart, product) row where variant IS NULL, and separately one
        (cart, product, variant) row per distinct variant -- adding the
        bare product and a specific variant of the same product must
        NOT collide."""
        product = make_product(stock_quantity=10)
        variant = make_variant(product=product, stock_quantity=10)
        self.client.post(self.url, {"product_id": product.id, "quantity": 1}, format="json")
        response = self.client.post(
            self.url, {"product_id": product.id, "variant_id": variant.id, "quantity": 1}, format="json"
        )
        self.assertEqual(len(response.data["items"]), 2)
        self.assertEqual(CartItem.objects.filter(product=product, variant__isnull=True).count(), 1)
        self.assertEqual(CartItem.objects.filter(product=product, variant=variant).count(), 1)

    def test_add_nonexistent_product_is_rejected(self):
        response = self.client.post(self.url, {"product_id": 999999, "quantity": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product", response.data)

    def test_add_nonexistent_variant_is_rejected(self):
        product = make_product()
        response = self.client.post(
            self.url, {"product_id": product.id, "variant_id": 999999, "quantity": 1}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("variant", response.data)

    def test_variant_belonging_to_a_different_product_is_rejected(self):
        product_a = make_product()
        product_b = make_product()
        variant_of_b = make_variant(product=product_b)
        response = self.client.post(
            self.url, {"product_id": product_a.id, "variant_id": variant_of_b.id, "quantity": 1}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("variant", response.data)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_inactive_product_cannot_be_added(self):
        product = make_product(is_active=False)
        response = self.client.post(self.url, {"product_id": product.id, "quantity": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_inactive_variant_cannot_be_added(self):
        product = make_product()
        variant = make_variant(product=product, is_active=False)
        response = self.client.post(
            self.url, {"product_id": product.id, "variant_id": variant.id, "quantity": 1}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_quantity_exceeding_stock_is_rejected(self):
        product = make_product(stock_quantity=3)
        response = self.client.post(self.url, {"product_id": product.id, "quantity": 5}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("3", str(response.data))
        self.assertEqual(CartItem.objects.count(), 0)

    def test_incrementing_past_available_stock_is_rejected(self):
        product = make_product(stock_quantity=5)
        self.client.post(self.url, {"product_id": product.id, "quantity": 3}, format="json")
        response = self.client.post(self.url, {"product_id": product.id, "quantity": 3}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # The original 3 must remain untouched -- a rejected increment
        # must not partially apply.
        self.assertEqual(CartItem.objects.get(product=product).quantity, 3)

    def test_out_of_stock_product_cannot_be_added(self):
        product = make_product(stock_quantity=0)
        response = self.client.post(self.url, {"product_id": product.id, "quantity": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_quantity_is_rejected_on_add(self):
        product = make_product()
        response = self.client.post(self.url, {"product_id": product.id, "quantity": 0}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_quantity_is_rejected_on_add(self):
        product = make_product()
        response = self.client.post(self.url, {"product_id": product.id, "quantity": -1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_client_supplied_price_is_ignored(self):
        """The write serializer (AddCartItemSerializer) has no price
        field at all -- there is nothing for a malicious/buggy client
        payload to override even if it tries."""
        product = make_product(price=100000)
        response = self.client.post(
            self.url,
            {"product_id": product.id, "quantity": 1, "price": 1, "unit_price": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["items"][0]["price_info"]["price"], 100000)
