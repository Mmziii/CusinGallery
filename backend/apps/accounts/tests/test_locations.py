"""Part R3 tests: province/city validation on addresses + the public
locations endpoint. Real behavior, not just status codes."""
from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import Address
from .helpers import make_user


def payload(**overrides):
    data = {
        "recipient_name": "Sara Ahmadi",
        "phone": "+989121234567",
        "province": "تهران",
        "city": "تهران",
        "address": "Valiasr St, No. 10",
        "postal_code": "1234567890",
        "unit": "3",
        "building_number": "12",
        "building_number": "10",
        "is_default": False,
    }
    data.update(overrides)
    return data


class LocationsEndpointTests(CacheIsolatedAPITestCase):
    def test_lists_all_31_provinces_with_cities(self):
        response = self.client.get(reverse("locations"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        provinces = response.json()["provinces"]
        self.assertEqual(len(provinces), 31)
        names = {p["name"] for p in provinces}
        self.assertIn("تهران", names)
        self.assertIn("فارس", names)
        self.assertTrue(all(p["cities"] for p in provinces))


class AddressLocationValidationTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989136666666")
        self.client.login(username="+989136666666", password="a-strong-passw0rd!")
        self.list_url = reverse("address-list")

    def test_known_province_and_city_accepted(self):
        response = self.client.post(self.list_url, payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unknown_province_rejected(self):
        response = self.client.post(
            self.list_url, payload(province="آتلانتیس"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("استان", str(response.json()))

    def test_known_city_of_other_province_rejected(self):
        response = self.client.post(
            self.list_url, payload(province="تهران", city="شیراز"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("شهر", str(response.json()))

    def test_free_text_city_is_allowed(self):
        # "سایر شهرها" free-text path must never block a customer.
        response = self.client.post(
            self.list_url, payload(province="فارس", city="روستای آبگرمو"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_english_alias_still_accepted(self):
        response = self.client.post(
            self.list_url, payload(province="Tehran", city="Tehran"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_legacy_address_stays_editable_without_touching_province_city(self):
        address = Address.objects.create(
            user=self.user,
            recipient_name="Old Customer",
            phone="+989121234567",
            province="Some Legacy Province",
            city="Legacy City",
            address="somewhere",
            postal_code="1234567890",
        )
        response = self.client.patch(
            reverse("address-detail", args=[address.pk]),
            {"recipient_name": "New Name"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        address.refresh_from_db()
        self.assertEqual(address.recipient_name, "New Name")
        self.assertEqual(address.province, "Some Legacy Province")
