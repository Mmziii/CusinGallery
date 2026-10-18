import importlib

from django.apps import apps
from django.urls import reverse

from apps.core.testing import CacheIsolatedAPITestCase
from apps.products.models import Product

from .models import Category


class CatalogRootIdentityTests(CacheIsolatedAPITestCase):
    @classmethod
    def setUpTestData(cls):
        migration = importlib.import_module("apps.categories.migrations.0006_kitchen_root_category")
        migration.backward(apps, None)
        cls.archive = Category.objects.create(name="بایگانی", slug="archive")
        cls.legacy = Category.objects.create(name="دسته قدیمی", slug="kitchen", parent=cls.archive)
        migration.forward(apps, None)
        cls.root = Category.objects.get(name="آشپزخانه", parent__isnull=True)
        cls.group = Category.objects.create(name="ظروف پخت", slug="cookware", parent=cls.root)
        cls.nested_namesake = Category.objects.create(name="آشپزخانه", slug="nested-kitchen", parent=cls.group)
        cls.product = Product.objects.create(name="قابلمه", slug="pot", sku="POT-ROOT", price=75000, stock_quantity=3, category=cls.group)

    def test_model_identity_uses_top_level_name_not_an_occupied_slug(self):
        self.assertEqual(self.root.slug, "kitchen-root")
        self.assertTrue(self.root.is_root)
        self.assertFalse(self.legacy.is_root)
        self.assertFalse(self.nested_namesake.is_root)

    def test_flat_and_detail_api_expose_the_real_root_flag(self):
        response = self.client.get(reverse("category-list"))
        self.assertEqual(response.status_code, 200)
        by_slug = {row["slug"]: row for row in response.data["results"]}
        self.assertTrue(by_slug["kitchen-root"]["is_root"])
        self.assertFalse(by_slug["kitchen"]["is_root"])
        self.assertFalse(by_slug["nested-kitchen"]["is_root"])
        detail = self.client.get(reverse("category-detail", args=["kitchen-root"]))
        self.assertTrue(detail.data["is_root"])

    def test_tree_exposes_one_flagged_root_and_unflagged_children(self):
        response = self.client.get(reverse("category-tree"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        root = response.data["results"][0]
        self.assertTrue(root["is_root"])
        self.assertEqual(root["slug"], "kitchen-root")
        self.assertTrue(all(not child["is_root"] for child in root["children"]))

    def test_flags_survive_suffixes_and_arbitrary_published_root_slugs(self):
        for slug in ("kitchen-root-2", "گروه-اصلی"):
            with self.subTest(slug=slug):
                self.root.slug = slug
                self.root.save(update_fields=["slug"])
                response = self.client.get(reverse("category-detail", args=[slug]))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data["is_root"])

    def test_product_ancestor_payload_marks_the_root_for_breadcrumb_links(self):
        response = self.client.get(reverse("product-detail", args=[self.product.slug]))
        self.assertEqual(response.status_code, 200)
        category = response.data["category"]
        self.assertFalse(category["is_root"])
        self.assertEqual(category["ancestors"], [{"slug": "kitchen-root", "name": "آشپزخانه", "is_root": True}])

    def test_filtering_the_real_root_uses_its_subtree_not_the_legacy_kitchen_slug(self):
        response = self.client.get(reverse("product-list"), {"category": "kitchen-root"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [self.product.pk])
        unrelated = self.client.get(reverse("product-list"), {"category": "kitchen"})
        self.assertEqual(unrelated.data["count"], 0)
