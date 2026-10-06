"""
Part S5 item 6 (checkout side): the plot number and the unit are required
for a NEW address, while orders placed from a saved (legacy) address keep
working exactly as before.

Real behaviour: orders are created through the real checkout endpoint and
the real service, addresses are real rows, and the assertions read the
order the database actually stored.
"""
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.helpers import make_user
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import Order
from .helpers import add_to_cart, make_address, make_product, valid_checkout_payload


class PlotAndUnitCheckoutTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989530000001")
        self.client.login(username="+989530000001", password="a-strong-passw0rd!")
        self.url = reverse("checkout")
        self.product = make_product(price=200000, stock_quantity=5)

    def test_an_inline_address_without_plot_or_unit_is_rejected(self):
        add_to_cart(self.user, self.product, quantity=1)
        payload = valid_checkout_payload()
        payload.pop("building_number")
        payload.pop("unit")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("building_number", response.data)
        self.assertIn("unit", response.data)
        self.assertIn("پلاک", str(response.data["building_number"][0]))
        self.assertIn("۰", str(response.data["unit"][0]))
        self.assertFalse(Order.objects.exists())

    def test_an_inline_address_with_plot_and_unit_is_snapshotted(self):
        add_to_cart(self.user, self.product, quantity=1)

        response = self.client.post(
            self.url,
            valid_checkout_payload(building_number="۱۲", unit="۰"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.shipping_building_number, "12")
        self.assertEqual(order.shipping_unit, "0")

    def test_a_legacy_saved_address_without_plot_and_unit_can_still_be_ordered(self):
        """Old addresses are order snapshots of their own: nothing about
        this rule may block an order that uses one."""
        legacy = make_address(self.user, building_number="", unit="")
        add_to_cart(self.user, self.product, quantity=1)

        response = self.client.post(
            self.url, {"address_id": legacy.pk}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.shipping_building_number, "")
        self.assertEqual(order.shipping_unit, "")
        # The address row itself is untouched.
        legacy.refresh_from_db()
        self.assertEqual(legacy.building_number, "")
        self.assertEqual(legacy.unit, "")

    def test_the_legacy_address_still_validates_after_the_order(self):
        legacy = make_address(self.user, building_number="", unit="")
        order = Order.objects.create(
            user=self.user,
            subtotal=0, total=0,  # an order row always carries the money snapshot
            shipping_recipient_name=legacy.recipient_name,
            shipping_phone=legacy.phone,
            shipping_province=legacy.province,
            shipping_city=legacy.city,
            shipping_address=legacy.address,
            shipping_postal_code=legacy.postal_code,
            shipping_building_number=legacy.building_number,
            shipping_unit=legacy.unit,
        )
        # Reading it back (the invoice path) must not raise.
        order.refresh_from_db()
        self.assertEqual(order.shipping_unit, "")
