from importlib import import_module
from types import SimpleNamespace

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.urls import reverse

from apps.core.testing import CacheIsolatedAPITestCase
from apps.products.models import Brand
from .helpers import make_brand, make_product


class BrandSlugTests(TestCase):
    def test_missing_slug_is_generated_without_losing_persian(self):
        brand = Brand.objects.create(name="برند ایرانی")
        self.assertEqual(brand.slug, "برند-ایرانی")
        brand.full_clean()

    def test_collisions_get_distinct_slugs_and_explicit_urls_never_change(self):
        first = Brand.objects.create(name="برند ایرانی", slug="برند-ایرانی")
        second = Brand.objects.create(name="برند ایرانی!")
        self.assertEqual(second.slug, "برند-ایرانی-2")
        first.name = "نام جدید"
        first.save()
        first.refresh_from_db()
        self.assertEqual(first.slug, "برند-ایرانی")

    def test_punctuation_only_name_has_a_nonempty_unique_fallback(self):
        first = Brand.objects.create(name="!!!")
        second = Brand.objects.create(name="؟؟؟")
        self.assertEqual(first.slug, "brand")
        self.assertEqual(second.slug, "brand-2")

    def test_generated_slug_is_saved_when_update_fields_is_used(self):
        brand = Brand.objects.create(name="نمونه", slug="old-url")
        Brand.objects.filter(pk=brand.pk).update(slug="")
        brand.refresh_from_db()
        brand.save(update_fields=["name"])
        brand.refresh_from_db()
        self.assertEqual(brand.slug, "نمونه")

    def test_slug_uniqueness_is_enforced_by_the_database(self):
        Brand.objects.create(name="اول", slug="same")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Brand.objects.create(name="دوم", slug="same")

    def test_data_migration_fills_legacy_blanks_and_is_idempotent(self):
        old_apps = MigrationExecutor(connection).loader.project_state(
            [("products", "0012_compact_featured_label")]
        ).apps
        OldBrand = old_apps.get_model("products", "Brand")
        published = OldBrand.objects.create(name="منتشرشده", slug="برند-ایرانی")
        blank = OldBrand.objects.create(name="برند ایرانی", slug="")
        whitespace = OldBrand.objects.create(name="برند ایرانی!", slug=" ")
        migration = import_module("apps.products.migrations.0013_fill_missing_brand_slugs")
        editor = SimpleNamespace(connection=connection)
        migration.fill_missing_brand_slugs(old_apps, editor)
        migration.fill_missing_brand_slugs(old_apps, editor)
        self.assertEqual(Brand.objects.get(pk=blank.pk).slug, "برند-ایرانی-2")
        self.assertEqual(Brand.objects.get(pk=whitespace.pk).slug, "برند-ایرانی-3")
        self.assertEqual(Brand.objects.get(pk=published.pk).slug, "برند-ایرانی")


class BrandProductFilterTests(CacheIsolatedAPITestCase):
    def test_filter_by_unicode_brand_slug_combines_with_price_and_stock(self):
        brand = make_brand(name="ایرانی", slug="برند-ایرانی")
        match = make_product(brand=brand, price=100000, stock_quantity=2)
        make_product(brand=brand, price=500000, stock_quantity=2)
        make_product(brand=brand, price=100000, stock_quantity=0)
        make_product(brand=make_brand(), price=100000, stock_quantity=2)
        response = self.client.get(reverse("product-list"), {
            "brand": brand.slug, "max_price": 200000, "in_stock": "true",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [match.pk])

    def test_inactive_or_unknown_brand_matches_no_products(self):
        brand = make_brand(is_active=False)
        product = make_product(brand=brand)
        for slug in (brand.slug, "unknown"):
            with self.subTest(slug=slug):
                response = self.client.get(reverse("product-list"), {"brand": slug})
                self.assertEqual(response.data["count"], 0)
        # No dangling link to an unpublished brand on an otherwise public product.
        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertIsNone(response.data["brand"])
