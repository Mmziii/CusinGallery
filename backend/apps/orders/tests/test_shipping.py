"""
Shipping method + delivery-window tests (Phase A corrections).

Covers three layers:
  1. apps.orders.shipping's pure functions (cost per method, delivery
     window, settings-driven behaviour, unknown-method handling);
  2. the checkout integration (client picks a method but never a price;
     cost + window are computed server-side and snapshotted on the Order);
  3. the shipping-methods endpoint the checkout UI renders its selector
     from.
"""
import datetime

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from .. import shipping
from ..models import Order
from .helpers import add_to_cart, make_product, make_user, valid_checkout_payload


class ShippingCostTests(TestCase):
    def test_standard_cost_below_threshold(self):
        self.assertEqual(
            shipping.calculate_shipping_cost(999999, "standard"),
            settings.STANDARD_SHIPPING_COST,
        )

    def test_standard_free_at_and_above_threshold(self):
        self.assertEqual(shipping.calculate_shipping_cost(1000000, "standard"), 0)
        self.assertEqual(shipping.calculate_shipping_cost(5000000, "standard"), 0)

    def test_standard_is_the_default_method(self):
        # The Phase 6 single-argument call must keep working unchanged.
        self.assertEqual(
            shipping.calculate_shipping_cost(100000),
            shipping.calculate_shipping_cost(100000, shipping.DEFAULT_METHOD),
        )

    def test_express_cost_is_fixed_even_above_free_threshold(self):
        # The free-shipping threshold is a standard-delivery promotion;
        # express keeps its fixed cost regardless of subtotal.
        self.assertEqual(shipping.calculate_shipping_cost(100000, "express"), settings.EXPRESS_SHIPPING_COST)
        self.assertEqual(shipping.calculate_shipping_cost(9000000, "express"), settings.EXPRESS_SHIPPING_COST)

    def test_unknown_method_raises(self):
        with self.assertRaises(ValueError):
            shipping.calculate_shipping_cost(100000, "teleport")

    @override_settings(
        SHIPPING_METHODS={
            "standard": {"cost": 70000, "free_threshold": 500000, "min_days": 2, "max_days": 4},
        }
    )
    def test_cost_is_settings_driven(self):
        self.assertEqual(shipping.calculate_shipping_cost(499999, "standard"), 70000)
        self.assertEqual(shipping.calculate_shipping_cost(500000, "standard"), 0)
        # express no longer configured -> unknown now
        with self.assertRaises(ValueError):
            shipping.calculate_shipping_cost(100000, "express")


class EstimatedDeliveryTests(TestCase):
    def test_window_from_explicit_date(self):
        day = datetime.date(2026, 10, 1)
        self.assertEqual(
            shipping.calculate_estimated_delivery("standard", from_date=day),
            (datetime.date(2026, 10, 4), datetime.date(2026, 10, 6)),
        )
        self.assertEqual(
            shipping.calculate_estimated_delivery("express", from_date=day),
            (datetime.date(2026, 10, 2), datetime.date(2026, 10, 3)),
        )

    def test_window_defaults_to_today(self):
        today = timezone.localdate()
        min_date, max_date = shipping.calculate_estimated_delivery("standard")
        self.assertEqual(min_date, today + datetime.timedelta(days=settings.SHIPPING_MIN_DELIVERY_DAYS))
        self.assertEqual(max_date, today + datetime.timedelta(days=settings.SHIPPING_MAX_DELIVERY_DAYS))

    def test_unknown_method_raises(self):
        with self.assertRaises(ValueError):
            shipping.calculate_estimated_delivery("teleport")

    def test_validation_helper(self):
        self.assertTrue(shipping.is_valid_shipping_method("standard"))
        self.assertTrue(shipping.is_valid_shipping_method("express"))
        self.assertFalse(shipping.is_valid_shipping_method("teleport"))


class ShippingMethodsEndpointTests(CacheIsolatedAPITestCase):
    def test_lists_configured_methods(self):
        response = self.client.get(reverse("shipping-methods"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["default"], "standard")
        by_id = {m["id"]: m for m in response.data["methods"]}
        self.assertEqual(by_id["standard"]["cost"], 50000)
        self.assertEqual(by_id["standard"]["free_threshold"], 1000000)
        self.assertEqual(by_id["standard"]["min_days"], 3)
        self.assertEqual(by_id["standard"]["max_days"], 5)
        self.assertEqual(by_id["express"]["cost"], 90000)
        self.assertIsNone(by_id["express"]["free_threshold"])

    @override_settings(
        SHIPPING_METHODS={
            "standard": {"cost": 1234, "free_threshold": None, "min_days": 1, "max_days": 2},
        }
    )
    def test_reflects_settings_changes(self):
        response = self.client.get(reverse("shipping-methods"))
        self.assertEqual([m["id"] for m in response.data["methods"]], ["standard"])
        self.assertEqual(response.data["methods"][0]["cost"], 1234)


class CheckoutShippingMethodTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989500000001")
        self.client.login(username="+989500000001", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def _checkout(self, payload):
        return self.client.post(self.url, payload, format="json")

    def test_default_method_is_standard_with_free_shipping(self):
        # 2 x 600000 = 1,200,000 subtotal -> above the free threshold.
        product = make_product(price=600000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=2)

        response = self._checkout(valid_checkout_payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.shipping_method, "standard")
        self.assertEqual(order.shipping_cost, 0)
        self.assertEqual(order.total, order.subtotal)

    def test_express_method_costs_money_even_above_threshold(self):
        product = make_product(price=600000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=2)

        response = self._checkout(valid_checkout_payload(shipping_method="express"))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.shipping_method, "express")
        self.assertEqual(order.shipping_cost, settings.EXPRESS_SHIPPING_COST)
        self.assertEqual(order.total, order.subtotal + settings.EXPRESS_SHIPPING_COST)

    def test_express_delivery_window_is_snapshotted(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        self._checkout(valid_checkout_payload(shipping_method="express"))

        order = Order.objects.get(user=self.user)
        today = timezone.localdate()
        self.assertEqual(order.estimated_delivery_min, today + datetime.timedelta(days=settings.EXPRESS_MIN_DELIVERY_DAYS))
        self.assertEqual(order.estimated_delivery_max, today + datetime.timedelta(days=settings.EXPRESS_MAX_DELIVERY_DAYS))
        # The API exposes the snapshot too.
        detail = self.client.get(reverse("order-detail", args=[order.id]))
        self.assertEqual(detail.data["shipping_method"], "express")
        self.assertEqual(detail.data["estimated_delivery_min"], str(order.estimated_delivery_min))
        self.assertEqual(detail.data["estimated_delivery_max"], str(order.estimated_delivery_max))

    def test_blank_shipping_method_falls_back_to_default(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        response = self._checkout(valid_checkout_payload(shipping_method=""))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.get(user=self.user).shipping_method, "standard")

    def test_invalid_shipping_method_is_rejected(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        response = self._checkout(valid_checkout_payload(shipping_method="teleport"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("shipping_method", response.data)
        self.assertEqual(Order.objects.count(), 0)

    def test_client_cannot_supply_a_shipping_cost(self):
        # Even if a client tries to inject a cost alongside the method,
        # the serializer has no such field -- checkout computes it.
        product = make_product(price=200000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        response = self._checkout(
            valid_checkout_payload(shipping_method="express", shipping_cost=1)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.get(user=self.user).shipping_cost, settings.EXPRESS_SHIPPING_COST)
