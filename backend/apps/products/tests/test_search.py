"""
Persian/Arabic search normalization tests (Part R5, item 7).

Covers the shared normalizer directly AND the live search endpoint (which
also powers the header's suggestions). Real behaviour only: every API
assertion checks which products actually come back, not just status codes.
"""
from django.urls import reverse
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import Product
from ..search import normalize_text
from .helpers import make_brand, make_category, make_product

ARABIC_YEH = "\u064A"       # ي
PERSIAN_YEH = "\u06CC"      # ی
ARABIC_KAF = "\u0643"       # ك
PERSIAN_KAF = "\u06A9"      # ک
ZWNJ = "\u200C"


class NormalizeTextUnitTests(CacheIsolatedAPITestCase):
    def test_arabic_yeh_and_kaf_map_to_persian(self):
        self.assertEqual(normalize_text("علي" + ARABIC_KAF), "علی" + PERSIAN_KAF)

    def test_alef_variants_unified(self):
        self.assertEqual(normalize_text("آأإا"), "اااا")

    def test_zwnj_zwj_tatweel_diacritics_removed(self):
        self.assertEqual(normalize_text("کتاب" + ZWNJ + "خانه"), "کتابخانه")
        # Diacritics dropped AND Arabic kaf mapped to Persian kaf.
        self.assertEqual(normalize_text("كِتَابٌ"), "کتاب")

    def test_persian_and_arabic_digits_to_ascii(self):
        self.assertEqual(normalize_text("۱۲۳"), "123")
        self.assertEqual(normalize_text("٤٥٦"), "456")

    def test_latin_casefold_and_whitespace_collapse(self):
        self.assertEqual(normalize_text("  Stainless   STEEL "), "stainless steel")

    def test_empty_and_none(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")


class SearchEndpointTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.url = reverse("product-list")
        self.cookware = make_category(name="ظروف پخت")
        self.brand = make_brand(name="یونیک")
        # ZWNJ in the stored name on purpose: normalizer must bridge it.
        self.spoon = make_product(
            category=self.cookware, brand=self.brand,
            name="قاشق" + ZWNJ + "چوبی یونیک", sku="SP-100",
            short_description="قاشق سرو چوبی",
        )
        self.pan = make_product(
            category=self.cookware, name="تابه گرانیتی", sku="PAN-200",
        )

    def names(self, response):
        return [row["name"] for row in response.json()["results"]]

    def search(self, term):
        return self.client.get(self.url, {"search": term})

    def test_search_by_plain_name(self):
        response = self.search("تابه")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.names(response), ["تابه گرانیتی"])

    def test_zwnj_query_matches_space_and_joined_forms(self):
        # Query with a space where the product stores a ZWNJ.
        self.assertIn(self.spoon.name, self.names(self.search("قاشق چوبی")))
        # Query fully joined.
        self.assertIn(self.spoon.name, self.names(self.search("قاشقچوبی")))

    def test_arabic_yeh_kaf_query_matches_persian_product(self):
        # "چوبی" spelled with Arabic yeh at the end.
        arabic_spelling = "قاشق چوب" + ARABIC_YEH
        self.assertIn(self.spoon.name, self.names(self.search(arabic_spelling)))

    def test_persian_digit_query_matches_ascii_sku(self):
        # SKU SP-100 found through Persian digits + Arabic kaf in "اس پی"?
        # Use the digit-mapping path on a numeric sku fragment.
        self.assertIn(self.spoon.name, self.names(self.search("۱۰۰")))

    def test_sku_exact_search(self):
        self.assertEqual(self.names(self.search("SP-100")), [self.spoon.name])

    def test_multi_token_order_independent(self):
        both_order_a = self.search("چوبی قاشق")
        both_order_b = self.search("قاشق چوبی")
        self.assertIn(self.spoon.name, self.names(both_order_a))
        self.assertIn(self.spoon.name, self.names(both_order_b))

    def test_token_must_all_match(self):
        # "چوبی" is only on the spoon; "تابه" only on the pan -> no product
        # contains both tokens.
        self.assertEqual(self.names(self.search("چوبی تابه")), [])

    def test_relevance_sku_beats_name_match(self):
        # A second product whose NAME mentions "pan-200" must still rank
        # below the product whose SKU is exactly PAN-200.
        make_product(category=self.cookware, name="ست هدیه PAN-200", sku="GIFT-1")
        names = self.names(self.search("PAN-200"))
        self.assertEqual(names[0], "تابه گرانیتی")

    def test_search_is_restricted_to_active_products(self):
        self.pan.is_active = False
        self.pan.save()
        self.assertEqual(self.names(self.search("تابه")), [])


class SearchIndexFreshnessTests(CacheIsolatedAPITestCase):
    """The index must stay fresh on save and on brand/category rename."""

    def setUp(self):
        self.category = make_category(name="ابزار آشپزخانه")
        self.brand = make_brand(name="پارس استیل")
        self.product = make_product(
            category=self.category, brand=self.brand,
            name="کتری روگازی", sku="KET-1",
        )

    def names(self, response):
        return [row["name"] for row in response.json()["results"]]

    def search(self, term):
        return self.client.get(reverse("product-list"), {"search": term})

    def test_index_includes_brand_and_category_names(self):
        self.assertIn(self.product.name, self.names(self.search("پارس استیل")))
        self.assertIn(self.product.name, self.names(self.search("ابزار آشپزخانه")))

    def test_brand_rename_propagates(self):
        self.brand.name = "آشپزخانه مدرن"
        self.brand.save()
        self.assertIn(self.product.name, self.names(self.search("آشپزخانه مدرن")))

    def test_category_rename_propagates(self):
        self.category.name = "لوازم پخت و پز"
        self.category.save()
        self.assertIn(self.product.name, self.names(self.search("لوازم پخت و پز")))

    def test_product_rename_updates_index(self):
        self.product.name = "قوری چینی"
        self.product.save()
        self.assertIn("قوری چینی", self.names(self.search("قوری")))


class BackfillCommandTests(CacheIsolatedAPITestCase):
    """The backfill command is idempotent and fills stale rows."""

    def test_backfill_fills_empty_and_is_idempotent(self):
        product = make_product(name="ماگ سرامیکی", sku="MUG-9")
        # Simulate a pre-R5 row with no index.
        Product.objects.filter(pk=product.pk).update(search_text="", search_name="")

        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("backfill_search_text", stdout=out)
        product.refresh_from_db()
        self.assertIn("ماگ", product.search_text)

        first = product.search_text
        out2 = StringIO()
        call_command("backfill_search_text", stdout=out2)
        product.refresh_from_db()
        self.assertEqual(product.search_text, first)
        self.assertIn("1/1", out.getvalue())   # first run filled the stale row
        self.assertIn("0/1", out2.getvalue())  # second run: nothing left to do
