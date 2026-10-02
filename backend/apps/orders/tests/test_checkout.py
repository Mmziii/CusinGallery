from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from ...cart.models import CartItem
from ..models import Order, OrderItem
from .helpers import add_to_cart, make_address, make_product, make_user, make_variant, valid_checkout_payload


class CheckoutAuthenticationTests(CacheIsolatedAPITestCase):
    def test_anonymous_cannot_checkout(self):
        response = self.client.post(reverse("checkout"), valid_checkout_payload(), format="json")
        # 403, not 401 -- SessionAuthentication is the only registered
        # authenticator in this project (see apps/accounts/tests for the
        # original explanation of this DRF behavior).
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SuccessfulCheckoutTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989300000001")
        self.client.login(username="+989300000001", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def test_checkout_with_inline_address_creates_order(self):
        product = make_product(price=200000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=2)

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        order = Order.objects.get(user=self.user)
        self.assertEqual(response.data["id"], order.id)
        self.assertTrue(order.order_number.startswith("CG-"))

    def test_checkout_starts_pending_and_unpaid(self):
        """Phase 6 explicitly does not touch payment status -- see
        apps.orders.services's module docstring."""
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.data["status"], Order.Status.PENDING)
        self.assertEqual(response.data["payment_status"], Order.PaymentStatus.UNPAID)

    def test_checkout_with_saved_address_id(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        address = make_address(self.user, city="Shiraz", postal_code="9876543210")

        response = self.client.post(self.url, {"address_id": address.id}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["shipping_city"], "Shiraz")
        self.assertEqual(response.data["shipping_postal_code"], "9876543210")

    def test_checkout_creates_order_items_matching_cart(self):
        product_a = make_product(name="Pot", price=150000, stock_quantity=5)
        product_b = make_product(name="Pan", price=90000, stock_quantity=5)
        add_to_cart(self.user, product_a, quantity=2)
        add_to_cart(self.user, product_b, quantity=1)

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(len(response.data["items"]), 2)
        names = {item["product_name"] for item in response.data["items"]}
        self.assertEqual(names, {"Pot", "Pan"})

    def test_checkout_clears_the_cart(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 0)

    def test_checkout_with_variant(self):
        product = make_product(price=100000)
        variant = make_variant(product=product, price=130000, stock_quantity=5)
        add_to_cart(self.user, product, variant=variant, quantity=1)

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        item = response.data["items"][0]
        self.assertEqual(item["variant_id"], variant.id)
        self.assertEqual(item["sku"], variant.sku)
        self.assertEqual(item["unit_price"], 130000)


class EmptyCartCheckoutTests(CacheIsolatedAPITestCase):
    def test_checkout_with_empty_cart_is_rejected(self):
        make_user(phone="+989300000002")
        self.client.login(username="+989300000002", password="a-strong-passw0rd!")

        response = self.client.post(reverse("checkout"), valid_checkout_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cart", response.data)
        self.assertEqual(Order.objects.count(), 0)


class UnavailableItemCheckoutTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989300000003")
        self.client.login(username="+989300000003", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def test_checkout_rejects_inactive_product(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        product.is_active = False
        product.save(update_fields=["is_active"])

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cart", response.data)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_rejects_inactive_variant(self):
        product = make_product()
        variant = make_variant(product=product, stock_quantity=5)
        add_to_cart(self.user, product, variant=variant, quantity=1)
        variant.is_active = False
        variant.save(update_fields=["is_active"])

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_rejects_insufficient_stock(self):
        """Item was added when 5 were in stock; stock later drops to 1
        (e.g. an admin correction) -- checkout must re-validate current
        stock, not trust what was true when the item was added to cart."""
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=5)
        product.stock_quantity = 1
        product.save(update_fields=["stock_quantity"])

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_with_one_unavailable_item_rejects_the_whole_order(self):
        """No partial checkout -- either the whole cart becomes an
        order, or none of it does."""
        available = make_product(name="Available", stock_quantity=5)
        unavailable = make_product(name="Unavailable", is_active=False)
        add_to_cart(self.user, available, quantity=1)
        add_to_cart(self.user, unavailable, quantity=1)

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        # The cart must remain untouched after a rejected checkout.
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 2)


class AddressValidationTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989300000004")
        self.other_user = make_user(phone="+989300000005")
        self.client.login(username="+989300000004", password="a-strong-passw0rd!")
        self.url = reverse("checkout")
        self.product = make_product(stock_quantity=5)
        add_to_cart(self.user, self.product, quantity=1)

    def test_using_another_users_address_id_is_rejected(self):
        other_address = make_address(self.other_user)
        response = self.client.post(self.url, {"address_id": other_address.id}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("address_id", response.data)
        self.assertEqual(Order.objects.count(), 0)

    def test_nonexistent_address_id_is_rejected(self):
        response = self.client.post(self.url, {"address_id": 999999}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("address_id", response.data)

    def test_incomplete_inline_address_is_rejected(self):
        response = self.client.post(self.url, {"recipient_name": "Sara"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("address_id", response.data)

    def test_invalid_postal_code_is_rejected(self):
        response = self.client.post(self.url, valid_checkout_payload(postal_code="abc"), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("postal_code", response.data)

    def test_no_address_information_at_all_is_rejected(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(STANDARD_SHIPPING_COST=50000, FREE_SHIPPING_THRESHOLD=1000000)
class ShippingAndPricingTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989300000006")
        self.client.login(username="+989300000006", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def test_subtotal_shipping_and_total_are_server_calculated(self):
        product = make_product(price=200000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=2)  # subtotal = 400000

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.data["subtotal"], 400000)
        self.assertEqual(response.data["shipping_cost"], 50000)
        self.assertEqual(response.data["discount_amount"], 0)
        self.assertEqual(response.data["total"], 450000)

    def test_free_shipping_threshold_zeroes_shipping_cost(self):
        product = make_product(price=1000000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)  # subtotal = 1000000, at threshold

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.data["shipping_cost"], 0)
        self.assertEqual(response.data["total"], 1000000)

    def test_just_below_free_shipping_threshold_still_charges_shipping(self):
        product = make_product(price=999999, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.data["shipping_cost"], 50000)

    def test_client_supplied_price_fields_are_ignored(self):
        """CheckoutSerializer has no price/total/subtotal/shipping_cost
        field at all -- there is nothing for a malicious payload to
        override even if it tries."""
        product = make_product(price=100000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        payload = valid_checkout_payload(subtotal=1, total=1, shipping_cost=0, discount_amount=999999)
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["subtotal"], 100000)
        self.assertEqual(response.data["total"], 150000)  # 100000 + 50000 shipping

    def test_sale_price_is_reflected_in_order_total(self):
        product = make_product(price=80000, compare_at_price=100000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        response = self.client.post(self.url, valid_checkout_payload(), format="json")

        self.assertEqual(response.data["items"][0]["unit_price"], 80000)
        self.assertEqual(response.data["subtotal"], 80000)


class SnapshotTests(CacheIsolatedAPITestCase):
    """Confirms Order/OrderItem are true snapshots -- later catalog
    changes must never retroactively alter a placed order, per master
    spec section 23."""

    def setUp(self):
        self.user = make_user(phone="+989300000007")
        self.client.login(username="+989300000007", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def test_order_survives_later_price_change(self):
        product = make_product(name="Snapshot Pot", price=150000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(self.url, valid_checkout_payload(), format="json")
        order_id = response.data["id"]

        product.price = 999999
        product.save(update_fields=["price"])

        detail = self.client.get(reverse("order-detail", args=[order_id]))
        self.assertEqual(detail.data["items"][0]["unit_price"], 150000)
        self.assertEqual(detail.data["subtotal"], 150000)

    def test_order_survives_later_product_deletion(self):
        product = make_product(name="Doomed Product", sku="DOOMED-SKU", price=75000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(self.url, valid_checkout_payload(), format="json")
        order_id = response.data["id"]

        product.delete()

        detail = self.client.get(reverse("order-detail", args=[order_id]))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        item = detail.data["items"][0]
        self.assertIsNone(item["product_id"])
        self.assertEqual(item["product_name"], "Doomed Product")
        self.assertEqual(item["sku"], "DOOMED-SKU")
        self.assertEqual(item["unit_price"], 75000)

    def test_order_survives_later_address_edit(self):
        address = make_address(self.user, city="Tehran")
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(self.url, {"address_id": address.id}, format="json")
        order_id = response.data["id"]

        address.city = "Mashhad"
        address.save(update_fields=["city"])

        detail = self.client.get(reverse("order-detail", args=[order_id]))
        self.assertEqual(detail.data["shipping_city"], "Tehran")


class ShippingSnapshotRegressionTests(CacheIsolatedAPITestCase):
    """
    Phase A regression: an order stores the shipping method, cost and
    delivery window that were in force WHEN IT WAS PLACED. Later changes
    to the shipping settings must never alter existing orders -- the
    values are snapshots, not live references.
    """

    def setUp(self):
        self.user = make_user(phone="+989300000090")
        self.client.login(username="+989300000090", password="a-strong-passw0rd!")
        # Below the free-shipping threshold so standard costs money.
        product = make_product(price=200000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(
            reverse("checkout"), valid_checkout_payload(shipping_method="standard"), format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        self.order = Order.objects.get(user=self.user)

    def test_shipping_cost_snapshot_survives_settings_change(self):
        from apps.orders import shipping as shipping_module

        original_cost = self.order.shipping_cost
        self.assertEqual(original_cost, settings.STANDARD_SHIPPING_COST)

        # The shop raises shipping prices and drops the free threshold...
        new_methods = {
            "standard": {"cost": 999999, "free_threshold": None, "min_days": 9, "max_days": 12},
        }
        with override_settings(SHIPPING_METHODS=new_methods):
            # ...the live calculation now reflects the new price...
            self.assertEqual(shipping_module.calculate_shipping_cost(200000, "standard"), 999999)
            # ...but the existing order keeps what the customer was charged.
            self.order.refresh_from_db()
            self.assertEqual(self.order.shipping_cost, original_cost)
            self.assertEqual(self.order.total, self.order.subtotal - self.order.discount_amount + original_cost)

    def test_estimated_delivery_snapshot_survives_settings_change(self):
        original_min = self.order.estimated_delivery_min
        original_max = self.order.estimated_delivery_max
        self.assertIsNotNone(original_min)
        self.assertIsNotNone(original_max)

        new_methods = {
            "standard": {"cost": 50000, "free_threshold": 1000000, "min_days": 30, "max_days": 40},
        }
        with override_settings(SHIPPING_METHODS=new_methods):
            self.order.refresh_from_db()
            self.assertEqual(self.order.estimated_delivery_min, original_min)
            self.assertEqual(self.order.estimated_delivery_max, original_max)
