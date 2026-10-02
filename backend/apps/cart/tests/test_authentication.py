from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from .helpers import make_user


class CartAuthenticationTests(CacheIsolatedAPITestCase):
    def test_anonymous_cannot_view_cart(self):
        response = self.client.get(reverse("cart"))
        # 403, not 401: SessionAuthentication is the only registered
        # authenticator (no BasicAuthentication), so DRF has no
        # WWW-Authenticate challenge to offer and downgrades
        # NotAuthenticated to PermissionDenied -- see
        # apps/accounts/tests/test_login_logout.py for the same,
        # already-established behavior in this project.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_add_item(self):
        response = self.client.post(reverse("cart-item-create"), {"product_id": 1, "quantity": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_clear_cart(self):
        response = self.client.delete(reverse("cart"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_update_or_remove_item(self):
        detail_url = reverse("cart-item-detail", args=[1])
        self.assertEqual(
            self.client.patch(detail_url, {"quantity": 2}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(detail_url).status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_can_view_own_cart(self):
        make_user(phone="+989100000001")
        self.client.login(username="+989100000001", password="a-strong-passw0rd!")
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["item_count"], 0)
