"""
Customer password policy tests (Part 1).

Customers: min 8 chars + ASCII only; digits-only IS allowed. Staff and
superusers keep Django's strict validators; login never applies policy.
"""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.core.testing import CacheIsolatedAPITestCase

from .helpers import make_user


class CustomerPasswordPolicyTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.register_url = reverse("register")
        self.change_url = reverse("change-password")

    def register(self, password):
        return self.client.post(
            self.register_url,
            {
                "phone": "+989123334444",
                "password": password,
                "password_confirm": password,
            },
            format="json",
        )

    def test_digits_only_password_is_accepted_for_customers(self):
        response = self.register("12345678")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

    def test_seven_characters_rejected_with_persian_message(self):
        response = self.register("abc123!")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("۸", str(response.content, "utf-8"))

    def test_persian_characters_rejected_with_keyboard_message(self):
        response = self.register("رمزعبور۱۲")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = str(response.content, "utf-8")
        self.assertIn("انگلیسی", body)
        self.assertIn("کیبورد", body)

    def test_change_password_applies_the_same_policy(self):
        user = make_user(phone="+989125556666", password="old-passw0rd!")
        self.client.login(username="+989125556666", password="old-passw0rd!")
        too_short = self.client.post(
            self.change_url,
            {
                "current_password": "old-passw0rd!",
                "new_password": "short1!",
                "new_password_confirm": "short1!",
            },
            format="json",
        )
        self.assertEqual(too_short.status_code, status.HTTP_400_BAD_REQUEST)
        persian = self.client.post(
            self.change_url,
            {
                "current_password": "old-passw0rd!",
                "new_password": "رمزجدید۱۲۳",
                "new_password_confirm": "رمزجدید۱۲۳",
            },
            format="json",
        )
        self.assertEqual(persian.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertTrue(user.check_password("old-passw0rd!"))

    def test_staff_passwords_stay_strict(self):
        """Django's AUTH_PASSWORD_VALIDATORS are untouched and still
        reject exactly what the customer policy deliberately allows."""
        with self.assertRaises(DjangoValidationError):
            validate_password("12345678")  # all-numeric: staff-only rule
        with self.assertRaises(DjangoValidationError):
            validate_password("password1")  # common password: staff-only rule

    @override_settings(AUTH_PASSWORD_VALIDATORS=[])
    def test_customer_policy_does_not_depend_on_django_validators(self):
        """Even with Django's validators disabled the customer rules
        (8 chars + ASCII) still hold -- they live in passwords.py."""
        response = self.register("رمزعبور۱۲")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_never_applies_the_policy(self):
        """A password created BEFORE (or outside) the policy must still
        log in -- policy changes never lock existing users out."""
        user = make_user(phone="+989127778888", password="کوتاه")
        user.set_password("کوتاه")  # non-ASCII, pre-policy password
        user.save()
        response = self.client.post(
            reverse("login"),
            {"identifier": "+989127778888", "password": "کوتاه"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
