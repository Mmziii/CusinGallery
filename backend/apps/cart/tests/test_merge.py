"""
Guest-cart merge tests (Part 1): POST /cart/merge/ sums guest lines
onto the server cart with per-line validation, stock capping, skip
reporting, token idempotency and strict per-user scoping.
"""
import uuid

from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.helpers import make_user
from apps.core.testing import CacheIsolatedAPITestCase
from apps.payments.tests.helpers import make_product
from apps.products.models import ProductVariant

from ..models import Cart


class MergeGuestCartTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.url = reverse("cart-merge")
        self.user = make_user(phone="+989126000001")
        self.client.login(username="+989126000001", password="a-strong-passw0rd!")

    def post_merge(self, lines, token=None):
        return self.client.post(
            self.url,
            {"lines": lines, "merge_token": token or str(uuid.uuid4())},
            format="json",
        )

    def cart_qty(self, product, variant=None):
        cart = Cart.objects.get(user=self.user)
        item = cart.items.filter(product=product, variant=variant).first()
        return item.quantity if item else 0

    def test_merge_requires_authentication(self):
        self.client.logout()
        response = self.client.post(self.url, {"lines": []}, format="json")
        self.assertIn(response.status_code, (401, 403))

    def test_merge_adds_new_lines_and_sums_existing_ones(self):
        product = make_product(stock_quantity=10)
        # Server cart already holds 2 of it:
        self.post_merge([{"product_id": product.pk, "variant_id": None, "quantity": 2}])
        self.assertEqual(self.cart_qty(product), 2)

        response = self.post_merge(
            [{"product_id": product.pk, "variant_id": None, "quantity": 3}]
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.cart_qty(product), 5)
        report = response.json()["report"]
        self.assertEqual(report["merged"][0]["added"], 3)
        self.assertEqual(report["adjusted"], [])
        self.assertEqual(report["skipped"], [])

    def test_merge_respects_stock_and_reports_the_cap(self):
        product = make_product(stock_quantity=4)
        response = self.post_merge(
            [{"product_id": product.pk, "variant_id": None, "quantity": 9}]
        )
        self.assertEqual(self.cart_qty(product), 4)
        report = response.json()["report"]
        self.assertEqual(report["adjusted"][0]["added"], 4)
        self.assertEqual(report["adjusted"][0]["reason"], "capped_by_stock")

    def test_merge_drops_inactive_products_and_foreign_variants(self):
        active = make_product(stock_quantity=5)
        inactive = make_product(slug="inactive-for-merge")
        inactive.is_active = False
        inactive.save()
        other = make_product(slug="other-for-merge")
        foreign_variant = ProductVariant.objects.create(
            product=other, sku="MV-1", price=1000, stock_quantity=5
        )

        response = self.post_merge(
            [
                {"product_id": inactive.pk, "variant_id": None, "quantity": 1},
                {"product_id": active.pk, "variant_id": foreign_variant.pk, "quantity": 1},
                {"product_id": active.pk, "variant_id": None, "quantity": 999},  # > per-line max
                {"nonsense": True},
                {"product_id": active.pk, "variant_id": None, "quantity": 2},
            ]
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        report = response.json()["report"]
        self.assertEqual(len(report["skipped"]), 4)
        reasons = {s.get("reason") for s in report["skipped"]}
        self.assertIn("unavailable", reasons)
        self.assertIn("too_many", reasons)
        self.assertIn("invalid", reasons)
        self.assertEqual(self.cart_qty(active), 2)
        self.assertEqual(Cart.objects.get(user=self.user).items.count(), 1)

    def test_merge_drops_out_of_stock_lines(self):
        product = make_product(stock_quantity=0)
        response = self.post_merge(
            [{"product_id": product.pk, "variant_id": None, "quantity": 1}]
        )
        report = response.json()["report"]
        self.assertEqual(report["skipped"][0]["reason"], "out_of_stock")
        self.assertEqual(self.cart_qty(product), 0)

    def test_double_merge_with_the_same_token_is_a_no_op(self):
        product = make_product(stock_quantity=10)
        token = str(uuid.uuid4())
        first = self.post_merge(
            [{"product_id": product.pk, "variant_id": None, "quantity": 2}], token=token
        )
        self.assertEqual(self.cart_qty(product), 2)

        second = self.post_merge(
            [{"product_id": product.pk, "variant_id": None, "quantity": 2}], token=token
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(self.cart_qty(product), 2, "replayed merge must not double lines")
        self.assertTrue(second.json()["report"]["replayed"])
        self.assertEqual(first.json()["cart"]["total"], second.json()["cart"]["total"])

    def test_different_tokens_merge_again(self):
        product = make_product(stock_quantity=10)
        self.post_merge([{"product_id": product.pk, "variant_id": None, "quantity": 2}])
        self.post_merge([{"product_id": product.pk, "variant_id": None, "quantity": 2}])
        self.assertEqual(self.cart_qty(product), 4)

    def test_merge_cannot_touch_another_users_cart(self):
        other = make_user(phone="+989126000002")
        product = make_product(stock_quantity=10)
        response = self.post_merge(
            [{"product_id": product.pk, "variant_id": None, "quantity": 1}]
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Cart.objects.filter(user=other).exists())
        # And logging in as the other user must not see our lines via a
        # fresh (empty) merge:
        self.client.logout()
        self.client.login(username="+989126000002", password="a-strong-passw0rd!")
        view = self.post_merge([], token=str(uuid.uuid4())).json()
        self.assertEqual(view["cart"]["items"], [])
