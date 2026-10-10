"""
Part S1 item 3 regression tests: "cannot add an address".

Reproduced first against the pre-fix behavior: POST with unit=null
answered 400 (null rejected by a blank-only CharField), a 9-digit
postal code was accepted, and Persian-digit phone/postal values were
stored verbatim (the old \\d regex matched Unicode digits). These tests
pin the fixed contract:

  * Persian/Arabic digits are normalized to ASCII before validation
  * postal code = exactly 10 digits (dashes/spaces tolerated)
  * phone = Iranian mobile (09xxxxxxxxx) or landline (0 + area code,
    11 digits); +98/0098 prefixes normalized
  * errors are Persian and field-keyed so the frontend can show them
    inline
"""
from django.urls import reverse
from rest_framework import status

from apps.accounts.models import Address
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
        # Part S5 item 6: plot/unit are required since this rule changed;
        # these tests are about phone/postal-code normalization.
        "building_number": "10",
        "unit": "3",
        "is_default": True,
    }
    base.update(overrides)
    return base


class PlotAndUnitRequiredTests(CacheIsolatedAPITestCase):
    """Part S5 item 6: a new address must have a plot number and a unit."""

    def setUp(self):
        self.user = make_user(phone="+989120002222")
        self.client.force_authenticate(self.user)
        self.url = reverse("address-list")

    def test_missing_plot_and_unit_are_rejected_with_persian_messages(self):
        data = payload()
        data.pop("building_number")
        data.pop("unit")
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("building_number", response.data)
        self.assertIn("unit", response.data)
        self.assertIn("پلاک", str(response.data["building_number"][0]))
        self.assertIn("۰", str(response.data["unit"][0]))

    def test_null_plot_and_unit_are_rejected_not_stored(self):
        response = self.client.post(
            self.url, payload(unit=None, building_number=None), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unit", response.data)
        self.assertIn("building_number", response.data)
        self.assertEqual(Address.objects.count(), 0)

    def test_zero_unit_and_a_plot_are_accepted_and_normalized(self):
        response = self.client.post(
            self.url, payload(unit="۰", building_number="۱۲"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["unit"], "0")
        self.assertEqual(response.data["building_number"], "12")

    def test_non_numeric_unit_is_rejected(self):
        response = self.client.post(self.url, payload(unit="الف"), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("فقط عدد", str(response.data["unit"][0]))

    def test_too_long_unit_is_rejected(self):
        response = self.client.post(self.url, payload(unit="1" * 21), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unit", response.data)

    def test_a_legacy_address_without_plot_and_unit_stays_editable(self):
        """Addresses saved before the rule must not become read-only: a
        PATCH that does not touch the empty values still succeeds."""
        legacy = Address.objects.create(
            user=self.user, recipient_name="قدیمی", phone="09120000000",
            province="تهران", city="تهران", address="آدرس قدیمی",
            postal_code="1234567890", unit="", building_number="",
        )
        url = reverse("address-detail", args=[legacy.pk])
        # A PATCH that touches other fields (province/city must stay a
        # consistent pair, see Part R3) must not be blocked by the empty
        # plot/unit the row already had.
        response = self.client.patch(
            url, {"address": "آدرس قدیمی ویرایش‌شده"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        legacy.refresh_from_db()
        self.assertEqual(legacy.address, "آدرس قدیمی ویرایش‌شده")
        self.assertEqual(legacy.unit, "")
        self.assertEqual(legacy.building_number, "")

    def test_filling_the_missing_values_on_a_legacy_address_works(self):
        legacy = Address.objects.create(
            user=self.user, recipient_name="قدیمی", phone="09120000000",
            province="تهران", city="تهران", address="آدرس قدیمی",
            postal_code="1234567890", unit="", building_number="",
        )
        url = reverse("address-detail", args=[legacy.pk])
        response = self.client.patch(
            url, {"unit": "۵", "building_number": "۹"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        legacy.refresh_from_db()
        self.assertEqual(legacy.unit, "5")
        self.assertEqual(legacy.building_number, "9")

    def test_clearing_an_existing_unit_is_rejected(self):
        address = Address.objects.create(
            user=self.user, recipient_name="گیرنده", phone="09120000000",
            province="تهران", city="تهران", address="آدرس",
            postal_code="1234567890", unit="3", building_number="10",
        )
        url = reverse("address-detail", args=[address.pk])
        response = self.client.patch(url, {"unit": ""}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unit", response.data)


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
            "unit": "۰",                # Part S5 item 6: «0» = no unit
            "building_number": "۱۲",
        }
        base.update(overrides)
        return base

    def test_inline_fields_are_normalized(self):
        serializer = CheckoutSerializer(data=self.inline())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["phone"], "09123456789")
        self.assertEqual(serializer.validated_data["postal_code"], "1234567890")
        self.assertEqual(serializer.validated_data["unit"], "0")
        self.assertEqual(serializer.validated_data["building_number"], "12")

    def test_inline_without_plot_or_unit_is_rejected_field_keyed(self):
        serializer = CheckoutSerializer(
            data=self.inline(unit=None, building_number=None)
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("building_number", serializer.errors)
        self.assertIn("unit", serializer.errors)
        self.assertIn("پلاک", str(serializer.errors["building_number"][0]))

    def test_inline_bad_postal_is_rejected_field_keyed(self):
        serializer = CheckoutSerializer(data=self.inline(postal_code="123456789"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("postal_code", serializer.errors)
