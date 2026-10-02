from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import CartItem
from ..services import get_or_create_cart
from .helpers import make_product, make_user, make_variant


class CartPricingTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989100000050")
        self.client.login(username="+989100000050", password="a-strong-passw0rd!")
        self.cart = get_or_create_cart(self.user)

    def test_line_total_and_subtotal_use_current_catalog_price(self):
        product = make_product(price=50000, stock_quantity=10)
        CartItem.objects.create(cart=self.cart, product=product, quantity=3)

        response = self.client.get(reverse("cart"))
        line = response.data["items"][0]
        self.assertEqual(line["price_info"]["price"], 50000)
        self.assertEqual(line["line_total"], 150000)
        self.assertEqual(response.data["subtotal"], 150000)
        self.assertEqual(response.data["total"], 150000)

    def test_sale_price_is_reflected_via_shared_pricing_mechanism(self):
        """Confirms the cart reuses apps.products.pricing rather than
        reimplementing sale/discount math -- same PriceInfo shape as
        the Phase 4 catalog API."""
        product = make_product(price=80000, compare_at_price=100000, discount_percentage=20, stock_quantity=5)
        CartItem.objects.create(cart=self.cart, product=product, quantity=2)

        response = self.client.get(reverse("cart"))
        info = response.data["items"][0]["price_info"]
        self.assertEqual(info["price"], 80000)
        self.assertEqual(info["compare_at_price"], 100000)
        self.assertTrue(info["is_on_sale"])
        self.assertEqual(response.data["items"][0]["line_total"], 160000)

    def test_price_changes_between_add_and_view_are_reflected_live(self):
        """The cart is NOT an order snapshot -- see master spec step 11.
        A price change after adding must show up on the next GET."""
        product = make_product(price=100000, stock_quantity=10)
        CartItem.objects.create(cart=self.cart, product=product, quantity=1)

        product.price = 70000
        product.save(update_fields=["price"])

        response = self.client.get(reverse("cart"))
        self.assertEqual(response.data["items"][0]["price_info"]["price"], 70000)
        self.assertEqual(response.data["subtotal"], 70000)

    def test_variant_with_price_override_uses_its_own_price_not_products(self):
        product = make_product(price=100000)
        variant = make_variant(product=product, price=85000, stock_quantity=5)
        CartItem.objects.create(cart=self.cart, product=product, variant=variant, quantity=1)

        response = self.client.get(reverse("cart"))
        self.assertEqual(response.data["items"][0]["price_info"]["price"], 85000)

    def test_unavailable_item_is_shown_but_excluded_from_subtotal(self):
        product = make_product(price=100000, stock_quantity=10)
        CartItem.objects.create(cart=self.cart, product=product, quantity=2)
        product.is_active = False
        product.save(update_fields=["is_active"])

        response = self.client.get(reverse("cart"))
        self.assertEqual(len(response.data["items"]), 1)
        line = response.data["items"][0]
        self.assertFalse(line["is_available"])
        self.assertEqual(line["unavailable_reason"], "product_unavailable")
        self.assertEqual(response.data["subtotal"], 0)

    def test_insufficient_stock_after_restock_change_is_flagged(self):
        """The item was added when 5 were in stock; stock later drops to
        1 (e.g. an admin correction) -- the stored quantity now exceeds
        what's available, and the cart must reflect that honestly rather
        than silently overselling."""
        product = make_product(price=100000, stock_quantity=5)
        CartItem.objects.create(cart=self.cart, product=product, quantity=5)
        product.stock_quantity = 1
        product.save(update_fields=["stock_quantity"])

        response = self.client.get(reverse("cart"))
        line = response.data["items"][0]
        self.assertFalse(line["is_available"])
        self.assertEqual(line["unavailable_reason"], "insufficient_stock")
        self.assertEqual(response.data["subtotal"], 0)

    def test_item_count_includes_unavailable_items_but_subtotal_does_not(self):
        available = make_product(price=50000, stock_quantity=10)
        unavailable = make_product(price=30000, is_active=False)
        CartItem.objects.create(cart=self.cart, product=available, quantity=2)
        CartItem.objects.create(cart=self.cart, product=unavailable, quantity=1)

        response = self.client.get(reverse("cart"))
        self.assertEqual(response.data["item_count"], 3)  # 2 + 1, informational
        self.assertEqual(response.data["subtotal"], 100000)  # only the available line

    def test_raw_stock_quantity_is_never_exposed_in_cart_response(self):
        product = make_product(price=100000, stock_quantity=37)
        CartItem.objects.create(cart=self.cart, product=product, quantity=1)

        response = self.client.get(reverse("cart"))
        body = str(response.data)
        self.assertNotIn("37", body)
        self.assertNotIn("stock_quantity", response.data["items"][0])

    def test_exact_stock_status_values(self):
        out_of_stock = make_product(price=1000, stock_quantity=0)
        in_stock = make_product(price=1000, stock_quantity=50, low_stock_threshold=5)
        CartItem.objects.create(cart=self.cart, product=out_of_stock, quantity=1)
        CartItem.objects.create(cart=self.cart, product=in_stock, quantity=1)

        response = self.client.get(reverse("cart"))
        by_product = {item["product"]["id"]: item for item in response.data["items"]}
        self.assertEqual(by_product[out_of_stock.id]["stock_status"], "out_of_stock")
        self.assertEqual(by_product[in_stock.id]["stock_status"], "in_stock")
