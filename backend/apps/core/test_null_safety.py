"""
Part S3 item 11: site-wide serializer safety net.

Regression guard for the address-form bug class -- clients that send
``null`` for an OPTIONAL text field used to get an opaque 400 "may not
be null". NullToBlankTextMixin (apps/core/serializers.py) coerces
None -> "" on every writable serializer's declared text fields, so the
same validation rules (and the same Persian messages) apply as when the
client had sent an empty string. This file exercises the rule through
the REAL endpoints across the three apps that take user-written text.
"""
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.helpers import make_user
from apps.core.testing import CacheIsolatedAPITestCase
from apps.products.tests.helpers import make_product


class NullOptionalTextTests(CacheIsolatedAPITestCase):
    def test_register_with_null_optional_names_and_email(self):
        """accounts: first_name/last_name/email sent as null are coerced
        to blank instead of rejected."""
        response = self.client.post(
            reverse("register"),
            {
                "phone": "09120001111",
                "password": "a-strong-passw0rd!",
                "password_confirm": "a-strong-passw0rd!",
                "first_name": None,
                "last_name": None,
                "email": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_profile_patch_null_names(self):
        user = make_user(first_name="سارا", last_name="محمدی")
        self.client.force_authenticate(user)
        response = self.client.patch(
            reverse("me"), {"first_name": None, "last_name": None}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "")
        self.assertEqual(user.last_name, "")

    def test_review_with_null_title_and_body(self):
        """reviews: title/body are optional; null must behave like ''."""
        user = make_user(phone="+989120000007")
        product = make_product()
        self.client.force_authenticate(user)
        response = self.client.post(
            reverse("review-create"),
            {"product_id": product.id, "rating": 4, "title": None, "body": None},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["title"], "")

    def test_password_reset_confirm_null_uid_token(self):
        """accounts: the reset-confirm serializer treats null uid/token
        like blank (and answers with its standard generic rejection, not
        a 'may not be null' 400)."""
        response = self.client.post(
            reverse("password-reset-confirm"),
            {
                "uid": None,
                "token": None,
                "new_password": "a-strong-passw0rd!",
                "new_password_confirm": "a-strong-passw0rd!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertNotIn("uid", body)  # not a field-level null complaint
        self.assertNotIn("token", body)


class PersianFieldKeyedMessagesTests(CacheIsolatedAPITestCase):
    """Validation messages must be Persian and keyed to the exact field."""

    def test_register_duplicate_phone_persian(self):
        make_user(phone="09120000002")
        response = self.client.post(
            reverse("register"),
            {
                "phone": "09120000002",
                "password": "a-strong-passw0rd!",
                "password_confirm": "a-strong-passw0rd!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.json())
        self.assertIn("قبلاً ساخته شده", " ".join(response.json()["phone"]))

    def test_register_password_mismatch_keyed_to_confirm_field(self):
        response = self.client.post(
            reverse("register"),
            {
                "phone": "09120003333",
                "password": "a-strong-passw0rd!",
                "password_confirm": "different-passw0rd!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("password_confirm", body)
        self.assertIn("یکسان نیستند", " ".join(body["password_confirm"]))

    def test_change_password_wrong_current_persian(self):
        user = make_user()
        self.client.force_authenticate(user)
        response = self.client.post(
            reverse("change-password"),
            {
                "current_password": "totally-wrong-pass!",
                "new_password": "another-strong-pass1!",
                "new_password_confirm": "another-strong-pass1!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("current_password", body)
        self.assertIn("نادرست است", " ".join(body["current_password"]))
