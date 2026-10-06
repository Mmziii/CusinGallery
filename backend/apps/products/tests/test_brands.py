from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from .helpers import make_brand


class BrandListDetailTests(CacheIsolatedAPITestCase):
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
        self.assertEqual(
            set(response.data.keys()),
            {"id", "name", "slug", "logo", "is_featured", "display_order", "tile_image"},
        )

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


class FeaturedBrandTilesTests(CacheIsolatedAPITestCase):
    """Part R2: /brands/?is_featured=true powers the home brand tiles."""

    def test_featured_filter_returns_only_featured_ordered_by_display_order(self):
        make_brand("Third", slug="third", is_featured=True, display_order=3)
        make_brand("First", slug="first", is_featured=True, display_order=1)
        make_brand("Not Featured", slug="not-featured")

        response = self.client.get(reverse("brand-list"), {"is_featured": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([b["name"] for b in response.data["results"]], ["First", "Third"])

    def test_without_filter_all_active_brands_are_returned(self):
        make_brand("A", slug="a", is_featured=True, display_order=1)
        make_brand("B", slug="b")
        response = self.client.get(reverse("brand-list"))
        self.assertEqual(len(response.data["results"]), 2)

    def test_inactive_featured_brand_is_never_exposed(self):
        make_brand("Ghost", slug="ghost", is_featured=True, is_active=False)
        response = self.client.get(reverse("brand-list"), {"is_featured": "true"})
        self.assertEqual(response.data["results"], [])


# Admin rendering needs {% static %} to resolve without a prebuilt
# whitenoise manifest (same trick as test_admin_products.py).
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


@override_settings(**PLAIN_STATIC)
class BrandAdminFeatureActionsTests(CacheIsolatedAPITestCase):
    """Part R2: bulk feature/unfeature actions + inline editing columns."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.admin = get_user_model().objects.create_superuser(
            username="+989100000000", phone="+989100000000", password="a-strong-passw0rd!"
        )
        self.client.login(username="+989100000000", password="a-strong-passw0rd!")

    def test_bulk_feature_and_unfeature_actions(self):
        brand = make_brand("Action Brand", slug="action-brand")
        changelist = reverse("admin:products_brand_changelist")

        response = self.client.post(
            changelist, {"action": "make_featured", "_selected_action": [brand.pk]}, follow=True
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        brand.refresh_from_db()
        self.assertTrue(brand.is_featured)

        self.client.post(
            changelist, {"action": "make_not_featured", "_selected_action": [brand.pk]}, follow=True
        )
        brand.refresh_from_db()
        self.assertFalse(brand.is_featured)

    def test_is_featured_and_display_order_are_inline_editable(self):
        from apps.products.admin import BrandAdmin

        self.assertIn("is_featured", BrandAdmin.list_editable)
        self.assertIn("display_order", BrandAdmin.list_editable)
        self.assertIn("is_featured", BrandAdmin.list_display)
        self.assertIn("display_order", BrandAdmin.list_display)
