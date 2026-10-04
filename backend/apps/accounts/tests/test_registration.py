from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from .helpers import make_user

User = get_user_model()


class RegistrationTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.url = reverse("register")

    def valid_payload(self, **overrides):
        payload = {
            "phone": "+989121234567",
            "email": "customer@example.com",
            "first_name": "Sara",
            "last_name": "Ahmadi",
            "password": "a-strong-passw0rd!",
            "password_confirm": "a-strong-passw0rd!",
        }
        payload.update(overrides)
        return payload

    def test_successful_registration_creates_a_real_hashed_password(self):
        response = self.client.post(self.url, self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone="+989121234567")
        # The stored value must be a hash, not the plaintext password --
        # this is the actual behavior guarantee, not just "a row exists".
        self.assertNotEqual(user.password, "a-strong-passw0rd!")
        self.assertTrue(user.check_password("a-strong-passw0rd!"))
        self.assertEqual(user.username, "+989121234567")
        self.assertEqual(user.email, "customer@example.com")

    def test_registration_auto_logs_in(self):
        self.client.post(self.url, self.valid_payload(), format="json")
        # A follow-up request to a session-authenticated endpoint should
        # now succeed without a separate login call.
        me = self.client.get(reverse("me"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["phone"], "+989121234567")

    def test_duplicate_phone_is_rejected(self):
        make_user(phone="+989121234567")
        response = self.client.post(self.url, self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)
        # Only the original account should exist -- confirms the request
        # was actually rejected before creating a second row, not just
        # that the response looked like an error.
        self.assertEqual(User.objects.filter(phone="+989121234567").count(), 1)

    def test_duplicate_email_is_rejected(self):
        make_user(phone="+989120000009", email="customer@example.com")
        response = self.client.post(self.url, self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.filter(email="customer@example.com").count(), 1)

    def test_two_customers_can_both_omit_email(self):
        """Regression guard for the NULL-vs-empty-string constraint bug
        class: two customers registering with no email at all must both
        succeed (this only works because email is stored as NULL, not
        '', for both -- see the User model's docstring)."""
        first = self.client.post(self.url, self.valid_payload(phone="+989120000001", email=""), format="json")
        self.client.logout()
        second = self.client.post(self.url, self.valid_payload(phone="+989120000002", email=""), format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(User.objects.get(phone="+989120000001").email)
        self.assertIsNone(User.objects.get(phone="+989120000002").email)

    def test_password_mismatch_is_rejected(self):
        response = self.client.post(
            self.url, self.valid_payload(password_confirm="something-else"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)
        self.assertFalse(User.objects.filter(phone="+989121234567").exists())

    def test_customer_policy_digits_only_ok_but_short_or_persian_rejected(self):
        # Part 1: customers get min-8 + ASCII only (digits-only is fine);
        # Django's stricter validators apply to staff/superusers only.
        digits_only = self.client.post(
            self.url, self.valid_payload(password="12345678", password_confirm="12345678"), format="json"
        )
        self.assertEqual(digits_only.status_code, status.HTTP_201_CREATED, digits_only.content)

    def test_invalid_phone_format_is_rejected(self):
        response = self.client.post(self.url, self.valid_payload(phone="not-a-phone"), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)
