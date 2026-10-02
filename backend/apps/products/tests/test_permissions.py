"""
Confirms the catalog API is genuinely read-only for everyone, including
authenticated staff -- per master spec section 16, catalog data is only
ever modified through Django Admin, never through this API. There is no
"staff can write via the API" escape hatch to test for, because none
exists (ReadOnlyModelViewSet everywhere in this app).
"""
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import make_brand, make_category, make_product

User = get_user_model()


class AnonymousCanBrowseTests(APITestCase):
    def test_anonymous_can_list_and_retrieve_products(self):
        make_product(name="Public Product", slug="public-product")
        self.assertEqual(self.client.get(reverse("product-list")).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(reverse("product-detail", args=["public-product"])).status_code,
            status.HTTP_200_OK,
        )

    def test_anonymous_can_list_and_retrieve_categories(self):
        make_category(name="Public Category", slug="public-category")
        self.assertEqual(self.client.get(reverse("category-list")).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(reverse("category-detail", args=["public-category"])).status_code,
            status.HTTP_200_OK,
        )

    def test_anonymous_can_list_and_retrieve_brands(self):
        make_brand(name="Public Brand", slug="public-brand")
        self.assertEqual(self.client.get(reverse("brand-list")).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(reverse("brand-detail", args=["public-brand"])).status_code,
            status.HTTP_200_OK,
        )


class NoOneCanModifyCatalogViaApiTests(APITestCase):
    """Covers both an anonymous visitor AND a logged-in, non-staff
    customer -- being authenticated must make no difference here."""

    def setUp(self):
        self.customer = User.objects.create_user(
            username="+989120000123", phone="+989120000123", password="a-strong-passw0rd!"
        )
        self.staff = User.objects.create_user(
            username="+989120000124", phone="+989120000124", password="a-strong-passw0rd!", is_staff=True
        )
        self.product = make_product(name="Protected", slug="protected")
        self.category = make_category(name="Protected Cat", slug="protected-cat")
        self.brand = make_brand(name="Protected Brand", slug="protected-brand")

    def _assert_all_writes_rejected(self, list_url, detail_url, payload):
        self.assertEqual(
            self.client.post(list_url, payload, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(detail_url, payload, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.put(detail_url, payload, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(self.client.delete(detail_url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_anonymous_cannot_modify_products(self):
        self._assert_all_writes_rejected(
            reverse("product-list"), reverse("product-detail", args=["protected"]), {"name": "Hacked"}
        )

    def test_logged_in_customer_cannot_modify_products(self):
        """The important case: being authenticated (but not staff) is
        NOT sufficient to write to the catalog -- there simply is no
        code path that would allow it, since the ViewSet is read-only
        regardless of who's asking."""
        self.client.login(username="+989120000123", password="a-strong-passw0rd!")
        self._assert_all_writes_rejected(
            reverse("product-list"), reverse("product-detail", args=["protected"]), {"name": "Hacked"}
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Protected")

    def test_staff_user_also_cannot_modify_products_via_this_api(self):
        """Being staff only ever matters for /admin/ -- this customer-
        facing catalog API has no staff-only write path either; product
        changes go through Django Admin, not this API, regardless of
        who's logged in."""
        self.client.login(username="+989120000124", password="a-strong-passw0rd!")
        self._assert_all_writes_rejected(
            reverse("product-list"), reverse("product-detail", args=["protected"]), {"name": "Hacked"}
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Protected")

    def test_anonymous_cannot_modify_categories(self):
        self._assert_all_writes_rejected(
            reverse("category-list"), reverse("category-detail", args=["protected-cat"]), {"name": "Hacked"}
        )

    def test_anonymous_cannot_modify_brands(self):
        self._assert_all_writes_rejected(
            reverse("brand-list"), reverse("brand-detail", args=["protected-brand"]), {"name": "Hacked"}
        )
