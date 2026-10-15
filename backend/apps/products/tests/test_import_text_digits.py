"""#17 The importer must not rewrite the digits in text columns.

``_normalize`` translated Persian/Arabic digits to ASCII for EVERY cell,
so a product named «ست ۳ عددی» was stored as «ست 3 عددی» and the same
rewriting hit the descriptions -- the text that customers actually read.

Only identifier and numeric columns need that translation (they are
compared against ASCII values already in the database); free text keeps
the digits the owner typed.
"""
from __future__ import annotations

import csv
import io
import tempfile

from django.test import TestCase, override_settings

from apps.categories.models import Category
from apps.products.importing import (
    _normalize,
    _text,
    import_products_from_rows,
    update_products_from_rows,
)
from apps.products.models import Brand, Product

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-media-import-digits-")

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.StaticFilesStorage"},
    }
}

HEADER = [
    "name", "slug", "sku", "category_slug", "brand_name", "price",
    "compare_at_price", "discount_percentage", "stock_quantity",
    "low_stock_threshold", "short_description", "description",
    "is_active", "is_featured",
]


def row(**overrides):
    base = {
        "name": "Pan", "slug": "pan", "sku": "SKU-1", "category_slug": "cookware",
        "brand_name": "", "price": "100000", "compare_at_price": "",
        "discount_percentage": "0", "stock_quantity": "5",
        "low_stock_threshold": "2", "short_description": "", "description": "",
        "is_active": "true", "is_featured": "false",
    }
    base.update(overrides)
    return base


class NormalizerContractTests(TestCase):
    """The two helpers, spelled out."""

    def test_text_keeps_the_digits_it_was_given(self):
        self.assertEqual(_text("ست ۳ عددی"), "ست ۳ عددی")
        self.assertEqual(_text("  ست ۳ عددی  "), "ست ۳ عددی")
        self.assertEqual(_text(None), "")

    def test_normalize_still_converts_identifiers(self):
        self.assertEqual(_normalize("SKU-۰۰۸"), "SKU-008")
        self.assertEqual(_normalize("۱۲۳۴۵"), "12345")

    def test_arabic_indic_digits_are_left_alone_in_text(self):
        self.assertEqual(_text("ست ٣ عددی"), "ست ٣ عددی")


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class ImportTextColumnTests(TestCase):
    """The visible symptom: names and descriptions came back re-written."""

    def setUp(self):
        self.category = Category.objects.create(name="Cookware", slug="cookware")

    def import_row(self, fetch=None, **overrides):
        result = import_products_from_rows([row(**overrides)], HEADER)
        self.assertTrue(result.ok, result.errors)
        return Product.objects.get(sku=fetch or overrides.get("sku", "SKU-1"))

    def test_the_name_keeps_its_persian_digits(self):
        product = self.import_row(name="ست ۳ عددی قابلمه", sku="SET-3")
        self.assertEqual(product.name, "ست ۳ عددی قابلمه")
        self.assertNotIn("3", product.name)

    def test_the_short_description_keeps_its_persian_digits(self):
        product = self.import_row(
            short_description="مناسب برای ۲ تا ۴ نفر", sku="SET-34"
        )
        self.assertEqual(product.short_description, "مناسب برای ۲ تا ۴ نفر")

    def test_the_description_keeps_its_persian_digits(self):
        product = self.import_row(
            description="گارانتی ۱۸ ماههٔ شرکتی.", sku="GR-18"
        )
        self.assertEqual(product.description, "گارانتی ۱۸ ماههٔ شرکتی.")

    def test_numbers_are_still_read_from_persian_digits(self):
        product = self.import_row(price="۱۲۰۰۰۰", stock_quantity="۱۵", sku="NUM-1")
        self.assertEqual(product.price, 120000)
        self.assertEqual(product.stock_quantity, 15)

    def test_the_sku_is_still_normalised(self):
        # an identifier: «SKU-۰۰۸» must land on the code the panel shows
        product = self.import_row(fetch="SKU-008", sku="SKU-۰۰۸")
        self.assertTrue(product.pk)

    def test_the_slug_is_still_normalised(self):
        product = self.import_row(slug="mahgo-۲", sku="SL-2")
        self.assertEqual(product.slug, "mahgo-2")

    def test_the_category_slug_is_still_normalised(self):
        Category.objects.create(name="Set", slug="set-2")
        product = self.import_row(category_slug="set-۲", sku="CAT-2")
        self.assertEqual(product.category_id, Category.objects.get(slug="set-2").pk)

    def test_a_brand_named_with_persian_digits_still_matches(self):
        brand = Brand.objects.create(name="برند ۱", slug="brand-1")
        product = self.import_row(brand_name="برند ۱", sku="BR-1")
        self.assertEqual(product.brand_id, brand.pk)

    def test_a_brand_named_with_ascii_digits_still_matches(self):
        """The same brand, found from a sheet typed the other way round."""
        brand = Brand.objects.create(name="برند 1", slug="brand-1")
        product = self.import_row(brand_name="برند ۱", sku="BR-1")
        self.assertEqual(product.brand_id, brand.pk)


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class UpdateTextColumnTests(TestCase):
    """The price/stock updater touches name, brand and category too."""

    def setUp(self):
        self.category = Category.objects.create(name="Cookware", slug="cookware")
        self.product = Product.objects.create(
            name="ماگ سرامیکی", slug="mug", sku="MUG-1",
            category=self.category, price=100000, stock_quantity=10,
        )
        self.header = ["sku", "name", "price", "sale_price", "stock", "brand", "category"]

    def update(self, text):
        reader = csv.DictReader(io.StringIO(text))
        result = update_products_from_rows(list(reader), self.header)
        self.assertTrue(result.ok, result.errors)
        self.product.refresh_from_db()
        return self.product

    def test_a_new_name_keeps_its_persian_digits(self):
        product = self.update("sku,name\nMUG-1,ست ۲ عددی\n")
        self.assertEqual(product.name, "ست ۲ عددی")

    def test_prices_typed_with_persian_digits_are_still_read(self):
        product = self.update("sku,price,stock\nMUG-1,۱۵۰۰۰۰,۱۲\n")
        self.assertEqual(product.price, 150000)
        self.assertEqual(product.stock_quantity, 12)

    def test_a_brand_is_found_from_a_persian_digit_name(self):
        brand = Brand.objects.create(name="کالای ۳", slug="kalaye-3")
        product = self.update("sku,brand\nMUG-1,کالای ۳\n")
        self.assertEqual(product.brand_id, brand.pk)

    def test_a_category_is_found_from_a_persian_digit_slug(self):
        other = Category.objects.create(name="ست", slug="set-2")
        product = self.update("sku,category\nMUG-1,set-۲\n")
        self.assertEqual(product.category_id, other.pk)
