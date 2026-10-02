from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import make_brand


class BrandListDetailTests(APITestCase):
    def test_list_returns_only_active_brands(self):
        make_brand("Zestware", is_active=True)
        make_brand("Discontinued Co", is_active=False)

        response = self.client.get(reverse("brand-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [b["name"] for b in response.data["results"]]
        self.assertEqual(names, ["Zestware"])

    def test_detail_lookup_by_slug(self):
        brand = make_brand("Persia Steel", slug="persia-steel")
        response = self.client.get(reverse("brand-detail", args=["persia-steel"]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], brand.id)
        self.assertEqual(response.data["name"], "Persia Steel")

    def test_inactive_brand_detail_is_not_found(self):
        make_brand("Hidden Brand", slug="hidden-brand", is_active=False)
        response = self.client.get(reverse("brand-detail", args=["hidden-brand"]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_brand_payload_does_not_expose_internal_fields(self):
        make_brand("Clean Brand", slug="clean-brand")
        response = self.client.get(reverse("brand-detail", args=["clean-brand"]))
        # Only public-facing fields -- no created_at/updated_at/is_active
        # leaking admin-only bookkeeping into the public API.
        self.assertEqual(set(response.data.keys()), {"id", "name", "slug", "logo"})

    def test_write_methods_are_not_allowed(self):
        brand = make_brand("Locked Brand", slug="locked-brand")
        list_url = reverse("brand-list")
        detail_url = reverse("brand-detail", args=["locked-brand"])

        self.assertEqual(
            self.client.post(list_url, {"name": "New", "slug": "new"}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(detail_url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        brand.refresh_from_db()
        self.assertEqual(brand.name, "Locked Brand")

    def test_anonymous_user_can_browse_brands(self):
        make_brand("Public Brand")
        response = self.client.get(reverse("brand-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
