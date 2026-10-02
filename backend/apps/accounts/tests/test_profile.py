from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import make_user


class ProfileTests(APITestCase):
    def setUp(self):
        self.me_url = reverse("me")
        self.user = make_user(phone="+989122222222", email="profile@example.com")
        self.client.login(username="+989122222222", password="a-strong-passw0rd!")

    def test_get_current_user_returns_expected_fields_and_no_username(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], "+989122222222")
        self.assertEqual(response.data["email"], "profile@example.com")
        self.assertEqual(response.data["first_name"], "Test")
        # `username` is deliberately not part of the public API shape.
        self.assertNotIn("username", response.data)

    def test_patch_updates_allowed_fields(self):
        response = self.client.patch(
            self.me_url, {"first_name": "Roya", "last_name": "Karimi"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Roya")
        self.assertEqual(self.user.last_name, "Karimi")

    def test_patch_cannot_change_phone(self):
        """Phone is excluded from ProfileUpdateSerializer -- a PATCH
        attempting to change it must be silently ignored, not applied and
        not erroring, since it's simply not a writable field here."""
        response = self.client.patch(self.me_url, {"phone": "+989129999999"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "+989122222222")

    def test_patch_rejects_duplicate_email(self):
        make_user(phone="+989123333333", email="taken@example.com")
        response = self.client.patch(self.me_url, {"email": "taken@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_patch_allows_clearing_email_to_null(self):
        response = self.client.patch(self.me_url, {"email": ""}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email)

    def test_put_is_not_allowed(self):
        response = self.client.put(self.me_url, {"first_name": "X"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_anonymous_cannot_patch_profile(self):
        self.client.logout()
        response = self.client.patch(self.me_url, {"first_name": "X"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
