"""
Pickup shipping method tests (Part 1): costs/windows per method,
checkout without a delivery address, workflow without tracking code for
pickup ONLY, ready-for-pickup notifications, and snapshot immutability.
"""
import datetime

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.core.models import SiteSettings
from apps.core.testing import CacheIsolatedAPITestCase
from apps.notifications.tests.helpers import install_fake_provider

from .. import shipping
from ..models import Order
from ..workflow import OrderWorkflowError, set_status
from .helpers import add_to_cart, make_product, make_user, valid_checkout_payload


class MethodConfigurationTests(CacheIsolatedAPITestCase):
    def test_pickup_costs_zero_and_never_counts_toward_free_shipping(self):
        self.assertEqual(shipping.calculate_shipping_cost(0, "pickup"), 0)
        self.assertEqual(shipping.calculate_shipping_cost(99999999, "pickup"), 0)

    def test_express_is_exactly_one_day(self):
        config = shipping.get_shipping_methods()["express"]
        self.assertEqual(config["min_days"], 1)
        self.assertEqual(config["max_days"], 1)
        self.assertIsNone(config["free_threshold"])

    def test_pickup_window_is_same_day_and_needs_no_address(self):
        config = shipping.get_shipping_methods()["pickup"]
        self.assertEqual((config["min_days"], config["max_days"]), (0, 0))
        self.assertFalse(config["requires_address"])

    def test_standard_window_still_comes_from_env(self):
        config = shipping.get_shipping_methods()["standard"]
        self.assertEqual(
            (config["min_days"], config["max_days"]),
            (
                settings_value("SHIPPING_MIN_DELIVERY_DAYS", 3),
                settings_value("SHIPPING_MAX_DELIVERY_DAYS", 5),
            ),
        )

    def test_methods_endpoint_exposes_labels_and_address_flag(self):
        response = self.client.get(reverse("shipping-methods"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        methods = {m["id"]: m for m in response.data["methods"]}
        self.assertEqual(set(methods), {"standard", "express", "pickup"})
        self.assertEqual(methods["pickup"]["label"], "حضوری")
        self.assertFalse(methods["pickup"]["requires_address"])
        self.assertEqual(methods["pickup"]["cost"], 0)


def settings_value(name, default):
    from django.conf import settings

    return getattr(settings, name, default)


class PickupCheckoutTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989510000001")
        self.client.login(username="+989510000001", password="a-strong-passw0rd!")
        self.url = reverse("checkout")

    def test_pickup_checkout_needs_only_name_and_phone(self):
        product = make_product(price=200000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)

        response = self.client.post(
            self.url,
            {
                "shipping_method": "pickup",
                "recipient_name": "Maryam Rezaei",
                "phone": "+989121112233",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.shipping_method, "pickup")
        self.assertEqual(order.shipping_cost, 0)
        self.assertEqual(order.total, order.subtotal)  # no shipping, no fee
        self.assertEqual(order.shipping_address, "")  # no delivery address snapshot
        self.assertEqual(order.shipping_recipient_name, "Maryam Rezaei")
        self.assertEqual(order.shipping_phone, "+989121112233")
        self.assertEqual(order.estimated_delivery_min, order.estimated_delivery_max)

    def test_pickup_without_name_is_rejected(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(
            self.url, {"shipping_method": "pickup", "phone": "+989121112233"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_standard_still_requires_a_full_address(self):
        product = make_product(stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        response = self.client.post(
            self.url,
            {"shipping_method": "standard", "recipient_name": "X", "phone": "+989121112233"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pickup_snapshot_is_immune_to_later_settings_changes(self):
        product = make_product(price=100000, stock_quantity=5)
        add_to_cart(self.user, product, quantity=1)
        self.client.post(
            self.url,
            {
                "shipping_method": "pickup",
                "recipient_name": "Maryam Rezaei",
                "phone": "+989121112233",
            },
            format="json",
        )
        order = Order.objects.get(user=self.user)

        methods = dict(shipping.get_shipping_methods())
        methods["pickup"] = {**methods["pickup"], "cost": 5000}
        with override_settings(SHIPPING_METHODS=methods):
            order.refresh_from_db()
            self.assertEqual(order.shipping_cost, 0)
            self.assertEqual(order.total, order.subtotal)


class PickupWorkflowTests(CacheIsolatedAPITestCase):
    def _order(self, method):
        user = make_user(phone="+989510000002")
        product = make_product(stock_quantity=5)
        add_to_cart(user, product, quantity=1)
        payload = valid_checkout_payload(shipping_method=method)
        if method == "pickup":
            payload = {
                "shipping_method": "pickup",
                "recipient_name": "Pickup Person",
                "phone": "+989121112233",
            }
        from ..services import checkout as do_checkout
        from ..serializers import CheckoutSerializer

        serializer = CheckoutSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return do_checkout(user, serializer.validated_data)

    def test_pickup_can_ship_without_a_tracking_code(self):
        order = self._order("pickup")
        set_status(order, Order.Status.CONFIRMED)
        set_status(order, Order.Status.PROCESSING)
        shipped = set_status(order, Order.Status.SHIPPED)  # must NOT raise
        self.assertEqual(shipped.status, Order.Status.SHIPPED)

    def test_courier_methods_still_require_tracking(self):
        order = self._order("standard")
        set_status(order, Order.Status.CONFIRMED)
        set_status(order, Order.Status.PROCESSING)
        with self.assertRaises(OrderWorkflowError):
            set_status(order, Order.Status.SHIPPED)


class PickupNotificationTests(CacheIsolatedAPITestCase):
    def test_shipped_becomes_ready_for_pickup_with_the_pickup_address(self):
        fake = install_fake_provider(self)
        site = SiteSettings.load()
        site.pickup_address = "تهران، خیابان ولیعصر، پلاک ۱۰"
        site.pickup_hours = "شنبه تا چهارشنبه ۹ تا ۱۷"
        site.save()

        user = make_user(phone="+989510000003")
        product = make_product(stock_quantity=5)
        add_to_cart(user, product, quantity=1)
        from ..serializers import CheckoutSerializer
        from ..services import checkout as do_checkout

        serializer = CheckoutSerializer(data={
            "shipping_method": "pickup",
            "recipient_name": "Pickup Person",
            "phone": "+989121112233",
        })
        serializer.is_valid(raise_exception=True)
        order = do_checkout(user, serializer.validated_data)

        with self.captureOnCommitCallbacks(execute=True):
            set_status(order, Order.Status.CONFIRMED)
            set_status(order, Order.Status.PROCESSING)
            set_status(order, Order.Status.SHIPPED)

        self.assertEqual(len(fake.sent), 1)
        message = fake.sent[0]["message"]
        self.assertIn("آمادهٔ دریافت حضوری", message)
        self.assertIn("تهران، خیابان ولیعصر، پلاک ۱۰", message)
        self.assertNotIn("کد رهگیری", message)

    def test_courier_shipped_message_unchanged(self):
        fake = install_fake_provider(self)
        user = make_user(phone="+989510000004")
        product = make_product(stock_quantity=5)
        add_to_cart(user, product, quantity=1)
        from ..serializers import CheckoutSerializer
        from ..services import checkout as do_checkout

        serializer = CheckoutSerializer(data=valid_checkout_payload(shipping_method="standard"))
        serializer.is_valid(raise_exception=True)
        order = do_checkout(user, serializer.validated_data)
        order.refresh_from_db()
        order.tracking_code = "POST-123"
        order.save(update_fields=["tracking_code"])

        with self.captureOnCommitCallbacks(execute=True):
            set_status(order, Order.Status.CONFIRMED)
            set_status(order, Order.Status.PROCESSING)
            set_status(order, Order.Status.SHIPPED)

        self.assertEqual(len(fake.sent), 1)
        self.assertIn("ارسال شد", fake.sent[0]["message"])
        self.assertIn("POST-123", fake.sent[0]["message"])
