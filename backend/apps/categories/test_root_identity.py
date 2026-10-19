import importlib

from django.apps import apps
from django.urls import reverse

from apps.core.testing import CacheIsolatedAPITestCase
from apps.products.models import Product

from .models import Category


class CatalogRootIdentityTests(CacheIsolatedAPITestCase):
    """Root identity is the ``is_catalog_root`` flag, never name/slug.

    Migration 0006 may create the root with ``kitchen``, ``kitchen-root``
    or a suffixed slug, and the owner may rename it afterwards; neither
    the API nor the storefront may infer the root from either field. The
    data step of migration 0007 flags that row -- replayed here by hand
    because the test rebuilds the root through 0006.
    """

    @classmethod
    def setUpTestData(cls):
        migration = importlib.import_module("apps.categories.migrations.0006_kitchen_root_category")
        migration.backward(apps, None)
        cls.archive = Category.objects.create(name="بایگانی", slug="archive")
        cls.legacy = Category.objects.create(name="دسته قدیمی", slug="kitchen", parent=cls.archive)
        migration.forward(apps, None)
        cls.root = Category.objects.get(name="آشپزخانه", parent__isnull=True)
        # What 0007's data step does once the root exists.
        Category.objects.filter(pk=cls.root.pk).update(is_catalog_root=True)
        cls.root.refresh_from_db()
        cls.group = Category.objects.create(name="ظروف پخت", slug="cookware", parent=cls.root)
        cls.nested_namesake = Category.objects.create(name="آشپزخانه", slug="nested-kitchen", parent=cls.group)
        cls.product = Product.objects.create(name="قابلمه", slug="pot", sku="POT-ROOT", price=75000, stock_quantity=3, category=cls.group)

    def test_model_identity_is_the_flag_not_a_slug_or_name(self):
        self.assertEqual(self.root.slug, "kitchen-root")
        self.assertTrue(self.root.is_catalog_root)
        self.assertEqual(Category.catalog_root(), self.root)
        self.assertFalse(self.legacy.is_catalog_root)
        self.assertFalse(self.nested_namesake.is_catalog_root)

    def test_flat_and_detail_api_expose_the_real_root_flag(self):
        response = self.client.get(reverse("category-list"))
        self.assertEqual(response.status_code, 200)
        by_slug = {row["slug"]: row for row in response.data["results"]}
        self.assertTrue(by_slug["kitchen-root"]["is_catalog_root"])
        self.assertFalse(by_slug["kitchen"]["is_catalog_root"])
        self.assertFalse(by_slug["nested-kitchen"]["is_catalog_root"])
        self.assertNotIn("is_root", by_slug["kitchen-root"])
        detail = self.client.get(reverse("category-detail", args=["kitchen-root"]))
        self.assertTrue(detail.data["is_catalog_root"])

    def test_tree_exposes_one_flagged_root_and_unflagged_children(self):
        response = self.client.get(reverse("category-tree"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        root = response.data["results"][0]
        self.assertTrue(root["is_catalog_root"])
        self.assertEqual(root["slug"], "kitchen-root")
        self.assertTrue(all(not child["is_catalog_root"] for child in root["children"]))

    def test_flag_survives_suffixes_and_arbitrary_published_root_slugs(self):
        for slug in ("kitchen-root-2", "گروه-اصلی"):
            with self.subTest(slug=slug):
                self.root.slug = slug
                self.root.save(update_fields=["slug"])
                response = self.client.get(reverse("category-detail", args=[slug]))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data["is_catalog_root"])

    def test_product_ancestor_payload_marks_the_root_for_breadcrumb_links(self):
        response = self.client.get(reverse("product-detail", args=[self.product.slug]))
        self.assertEqual(response.status_code, 200)
        category = response.data["category"]
        self.assertFalse(category["is_catalog_root"])
        self.assertEqual(
            category["ancestors"],
            [{"slug": "kitchen-root", "name": "آشپزخانه", "is_catalog_root": True}],
        )

    def test_filtering_the_real_root_uses_its_subtree_not_the_legacy_kitchen_slug(self):
        response = self.client.get(reverse("product-list"), {"category": "kitchen-root"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [self.product.pk])
        unrelated = self.client.get(reverse("product-list"), {"category": "kitchen"})
        self.assertEqual(unrelated.data["count"], 0)
