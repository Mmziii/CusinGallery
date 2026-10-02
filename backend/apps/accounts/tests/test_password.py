from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import make_user


class ChangePasswordTests(APITestCase):
    def setUp(self):
        self.url = reverse("change-password")
        self.user = make_user(phone="+989124444444")
        self.client.login(username="+989124444444", password="a-strong-passw0rd!")

    def test_change_password_success(self):
        response = self.client.post(
            self.url,
            {
                "current_password": "a-strong-passw0rd!",
                "new_password": "another-strong-pw2!",
                "new_password_confirm": "another-strong-pw2!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("another-strong-pw2!"))
        self.assertFalse(self.user.check_password("a-strong-passw0rd!"))

    def test_change_password_keeps_the_session_alive(self):
        """update_session_auth_hash must be called -- otherwise the
        session that just changed its own password would immediately be
        invalidated by Django's own session-auth-hash check."""
        self.client.post(
            self.url,
            {
                "current_password": "a-strong-passw0rd!",
                "new_password": "another-strong-pw2!",
                "new_password_confirm": "another-strong-pw2!",
            },
            format="json",
        )
        me = self.client.get(reverse("me"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)

    def test_change_password_rejects_wrong_current_password(self):
        response = self.client.post(
            self.url,
            {
                "current_password": "totally-wrong",
                "new_password": "another-strong-pw2!",
                "new_password_confirm": "another-strong-pw2!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("a-strong-passw0rd!"))

    def test_change_password_rejects_mismatched_confirmation(self):
        response = self.client.post(
            self.url,
            {
                "current_password": "a-strong-passw0rd!",
                "new_password": "another-strong-pw2!",
                "new_password_confirm": "does-not-match",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_enforces_strength_validators(self):
        response = self.client.post(
            self.url,
            {"current_password": "a-strong-passw0rd!", "new_password": "12345678", "new_password_confirm": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_cannot_change_password(self):
        self.client.logout()
        response = self.client.post(
            self.url,
            {"current_password": "x", "new_password": "y", "new_password_confirm": "y"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PasswordResetTests(APITestCase):
    def setUp(self):
        self.request_url = reverse("password-reset-request")
        self.confirm_url = reverse("password-reset-confirm")

    def test_reset_request_for_account_with_email_sends_a_real_email(self):
        make_user(phone="+989125555555", email="reset@example.com")
        response = self.client.post(self.request_url, {"identifier": "reset@example.com"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Uses Django's configured EMAIL_BACKEND -- the test runner's
        # locmem backend captures it, proving a real send_mail() call
        # happened, not just that the view returned 200.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset@example.com", mail.outbox[0].to)
        self.assertIn("reset-password/confirm", mail.outbox[0].body)

    def test_reset_request_for_unknown_identifier_returns_same_generic_response(self):
        response = self.client.post(self.request_url, {"identifier": "nobody@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_request_for_phone_only_account_sends_no_email_but_still_succeeds(self):
        make_user(phone="+989126666666")  # no email
        response = self.client.post(self.request_url, {"identifier": "+989126666666"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)  # honestly reflects that no SMS provider exists

    def test_confirm_with_valid_token_actually_changes_the_password(self):
        user = make_user(phone="+989127777777", password="old-passw0rd!")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.post(
            self.confirm_url,
            {
                "uid": uid,
                "token": token,
                "new_password": "brand-new-passw0rd!",
                "new_password_confirm": "brand-new-passw0rd!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password("brand-new-passw0rd!"))
        self.assertFalse(user.check_password("old-passw0rd!"))

    def test_confirm_with_invalid_token_is_rejected(self):
        user = make_user(phone="+989128888888")
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        response = self.client.post(
            self.confirm_url,
            {
                "uid": uid,
                "token": "not-a-real-token",
                "new_password": "brand-new-passw0rd!",
                "new_password_confirm": "brand-new-passw0rd!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertTrue(user.check_password("a-strong-passw0rd!"))

    def test_confirm_token_cannot_be_reused_after_password_already_changed(self):
        """Django's default token generator invalidates a token once the
        password it was issued for has changed -- a real security
        property worth asserting, not just token-format validity."""
        user = make_user(phone="+989129999998", password="old-passw0rd!")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        first = self.client.post(
            self.confirm_url,
            {"uid": uid, "token": token, "new_password": "first-new-pw!", "new_password_confirm": "first-new-pw!"},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self.client.post(
            self.confirm_url,
            {"uid": uid, "token": token, "new_password": "second-new-pw!", "new_password_confirm": "second-new-pw!"},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
