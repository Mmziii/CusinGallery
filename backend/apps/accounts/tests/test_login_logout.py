from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from .helpers import make_user


class LoginLogoutTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.login_url = reverse("login")
        self.logout_url = reverse("logout")
        self.me_url = reverse("me")
        self.user = make_user(phone="+989121111111", email="login@example.com", password="a-strong-passw0rd!")

    def test_login_with_phone_succeeds_and_starts_a_session(self):
        response = self.client.post(
            self.login_url, {"identifier": "+989121111111", "password": "a-strong-passw0rd!"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], "+989121111111")
        # The session actually works for a subsequent request, not just
        # that login() returned 200.
        me = self.client.get(self.me_url)
        self.assertEqual(me.status_code, status.HTTP_200_OK)

    def test_login_with_email_succeeds(self):
        response = self.client.post(
            self.login_url, {"identifier": "login@example.com", "password": "a-strong-passw0rd!"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(
            self.login_url, {"identifier": "+989121111111", "password": "totally-wrong"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Must not have established a session.
        me = self.client.get(self.me_url)
        self.assertEqual(me.status_code, status.HTTP_403_FORBIDDEN)

    def test_login_with_unknown_identifier_fails_with_generic_message(self):
        response = self.client.post(
            self.login_url, {"identifier": "+989129999999", "password": "whatever"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Same error shape as a wrong-password response -- the API must
        # not reveal whether the identifier exists at all.
        body = str(response.data)
        self.assertNotIn("does not exist", body.lower())

    def test_login_rejects_inactive_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            self.login_url, {"identifier": "+989121111111", "password": "a-strong-passw0rd!"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_ends_the_session(self):
        self.client.post(
            self.login_url, {"identifier": "+989121111111", "password": "a-strong-passw0rd!"}, format="json"
        )
        self.assertEqual(self.client.get(self.me_url).status_code, status.HTTP_200_OK)

        logout_response = self.client.post(self.logout_url)
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        # The critical assertion: the *same client* (same cookies) can no
        # longer reach a protected endpoint after logout.
        after_logout = self.client.get(self.me_url)
        self.assertEqual(after_logout.status_code, status.HTTP_403_FORBIDDEN)

    def test_logout_requires_authentication(self):
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_access_current_user_endpoint(self):
        response = self.client.get(self.me_url)
        # 403, not 401: with SessionAuthentication as the only configured
        # authenticator (no BasicAuthentication), DRF has no
        # WWW-Authenticate challenge to offer, so it downgrades the
        # NotAuthenticated exception to PermissionDenied (403) rather
        # than issuing a 401 with no header -- see DRF's
        # APIView.handle_exception. This is standard, expected behavior
        # for a session-only API, not a bug.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
