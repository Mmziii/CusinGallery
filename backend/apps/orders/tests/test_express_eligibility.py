from django.test import SimpleTestCase
from django.urls import reverse

from apps.core.testing import CacheIsolatedAPITestCase

from .. import shipping
from ..models import Order
from ..services import CheckoutError, checkout
from .helpers import add_to_cart, make_address, make_product, make_user, valid_checkout_payload


class ExpressDestinationTests(SimpleTestCase):
    def test_tehran_city_and_legacy_aliases_are_eligible(self):
        for province, city in (("تهران", "تهران"), (" Tehran ", "TEHRAN"), ("تهران", "شهرستان تهران"), ("تهران", "شهرستان  تهران")):
            with self.subTest(province=province, city=city):
                self.assertTrue(shipping.is_express_eligible(province, city))

    def test_other_cities_and_provinces_and_partial_names_are_not_eligible(self):
        for province, city in (("تهران", "شهریار"), ("تهران", "ری"), ("تهران", "پردیس"), ("تهران", "دماوند"), ("البرز", "تهران"), ("تهران", "تهرانپارس"), ("تهران", "تهران - ری"), (None, None), ("تهران", "")):
            with self.subTest(province=province, city=city):
                self.assertFalse(shipping.is_express_eligible(province, city))


class ExpressCheckoutEligibilityTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(self.user)
        self.product = make_product(price=200000, stock_quantity=5)
        self.cart_item = add_to_cart(self.user, self.product, quantity=1)
        self.url = reverse("checkout")

    def assert_rejected_without_mutation(self, payload):
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["shipping_method"], ["ارسال اکسپرس فعلاً فقط برای شهر تهران"])
        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)
        self.cart_item.refresh_from_db()
        self.assertEqual(self.cart_item.quantity, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

    def test_inline_tehran_city_can_order_express(self):
        response = self.client.post(self.url, valid_checkout_payload(province="تهران", city="تهران", shipping_method="express"), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["shipping_method"], "express")

    def test_owned_saved_tehran_address_uses_legacy_aliases(self):
        address = make_address(self.user, province="Tehran", city="Tehran")
        response = self.client.post(self.url, {"address_id": address.pk, "shipping_method": "express"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["shipping_method"], "express")

    def test_other_city_in_tehran_province_cannot_order_express(self):
        self.assert_rejected_without_mutation(valid_checkout_payload(province="تهران", city="شهریار", shipping_method="express"))

    def test_city_tehran_in_another_province_cannot_order_express(self):
        self.assert_rejected_without_mutation(valid_checkout_payload(province="البرز", city="تهران", shipping_method="express"))

    def test_inline_fields_cannot_override_the_saved_destination(self):
        address = make_address(self.user, province="تهران", city="ری")
        self.assert_rejected_without_mutation({"address_id": address.pk, "province": "تهران", "city": "تهران", "shipping_method": "express"})

    def test_address_changed_after_selection_is_rechecked_on_the_server(self):
        address = make_address(self.user, province="تهران", city="تهران")
        address.city = "پردیس"
        address.save(update_fields=["city"])
        self.assert_rejected_without_mutation({"address_id": address.pk, "shipping_method": "express"})

    def test_business_service_also_enforces_the_rule_without_a_serializer(self):
        with self.assertRaises(CheckoutError) as caught:
            checkout(self.user, valid_checkout_payload(province="تهران", city="دماوند", shipping_method="express"))
        self.assertEqual(caught.exception.errors, {"shipping_method": [shipping.EXPRESS_UNAVAILABLE_MESSAGE]})
        self.cart_item.refresh_from_db()
        self.assertEqual(Order.objects.count(), 0)

    def test_standard_delivery_outside_tehran_is_unchanged(self):
        response = self.client.post(self.url, valid_checkout_payload(province="اصفهان", city="اصفهان", shipping_method="standard"), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["shipping_method"], "standard")
        self.assertEqual(response.data["shipping_city"], "اصفهان")

    def test_pickup_without_any_delivery_address_is_unchanged(self):
        response = self.client.post(self.url, {"recipient_name": "سارا", "phone": "09121112233", "shipping_method": "pickup"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["shipping_method"], "pickup")
        self.assertEqual(response.data["shipping_cost"], 0)
        self.assertEqual(response.data["shipping_city"], "")
