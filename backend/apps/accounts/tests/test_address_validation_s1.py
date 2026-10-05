"""
Part S1 item 3 regression tests: "cannot add an address".

Reproduced first against the pre-fix behavior: POST with unit=null
answered 400 (null rejected by a blank-only CharField), a 9-digit
postal code was accepted, and Persian-digit phone/postal values were
stored verbatim (the old \\d regex matched Unicode digits). These tests
pin the fixed contract:

  * null/blank unit + building_number are accepted and stored as ""
  * Persian/Arabic digits are normalized to ASCII before validation
  * postal code = exactly 10 digits (dashes/spaces tolerated)
  * phone = Iranian mobile (09xxxxxxxxx) or landline (0 + area code,
    11 digits); +98/0098 prefixes normalized
  * errors are Persian and field-keyed so the frontend can show them
    inline
"""
from django.urls import reverse
from rest_framework import status

from apps.core.testing import CacheIsolatedAPITestCase
from apps.orders.serializers import CheckoutSerializer

from .helpers import make_user


def payload(**overrides):
    base = {
        "recipient_name": "گیرنده تست",
        "phone": "09123456789",
        "province": "تهران",
        "city": "تهران",
        "address": "خیابان ولیعصر، پلاک 10",
        "postal_code": "1234567890",
        "is_default": True,
    }
    base.update(overrides)
    return base


class AddressNullOptionalFieldsTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989120002222")
        self.client.force_authenticate(self.user)
        self.url = reverse("address-list")

    def test_null_unit_and_building_number_are_stored_as_empty(self):
        response = self.client.post(
            self.url, payload(unit=None, building_number=None), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["unit"], "")
        self.assertEqual(response.data["building_number"], "")

    def test_absent_optional_fields_still_work(self):
        response = self.client.post(self.url, payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class AddressNormalizationTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989120003333")
        self.client.force_authenticate(self.user)
        self.url = reverse("address-list")

    def test_persian_digit_phone_is_normalized_to_ascii(self):
        response = self.client.post(
            self.url, payload(phone="۰۹۱۲۳۴۵۶۷۸۹"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["phone"], "09123456789")

    def test_persian_digit_postal_with_dash_is_normalized(self):
        response = self.client.post(
            self.url, payload(postal_code="۱۲۳۴-۵۶۷۸۹۰"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["postal_code"], "1234567890")

    def test_plus98_mobile_is_normalized_to_zero_form(self):
        response = self.client.post(
            self.url, payload(phone="+989123456789"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["phone"], "09123456789")

    def test_landline_with_area_code_is_accepted(self):
        response = self.client.post(
            self.url, payload(phone="02112345678"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["phone"], "02112345678")


class AddressRejectionTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.user = make_user(phone="+989120004444")
        self.client.force_authenticate(self.user)
        self.url = reverse("address-list")

    def test_nine_digit_postal_is_rejected_with_persian_field_message(self):
        response = self.client.post(
            self.url, payload(postal_code="123456789"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("postal_code", response.data)
        message = str(response.data["postal_code"][0])
        self.assertIn("۱۰ رقم", message)

    def test_too_short_phone_is_rejected_field_keyed(self):
        response = self.client.post(self.url, payload(phone="0912345678"), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)
        message = str(response.data["phone"][0])
        self.assertIn("موبایل ایرانی", message)

    def test_non_digit_phone_is_rejected(self):
        response = self.client.post(
            self.url, payload(phone="not-a-phone"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)


class CheckoutInlineAddressTests(CacheIsolatedAPITestCase):
    """The one-off checkout address must obey the exact same rules."""

    def inline(self, **overrides):
        base = {
            "recipient_name": "گیرنده",
            "phone": "۰۹۱۲۳۴۵۶۷۸۹",  # Persian digits on purpose
            "province": "تهران",
            "city": "تهران",
            "address": "آدرس",
            "postal_code": "۱۲۳۴۵۶۷۸۹۰",
            "unit": None,                 # JSON null must be tolerated
            "building_number": None,
        }
        base.update(overrides)
        return base

    def test_inline_fields_are_normalized_and_null_tolerated(self):
        serializer = CheckoutSerializer(data=self.inline())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["phone"], "09123456789")
        self.assertEqual(serializer.validated_data["postal_code"], "1234567890")
        self.assertEqual(serializer.validated_data["unit"], "")
        self.assertEqual(serializer.validated_data["building_number"], "")

    def test_inline_bad_postal_is_rejected_field_keyed(self):
        serializer = CheckoutSerializer(data=self.inline(postal_code="123456789"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("postal_code", serializer.errors)
