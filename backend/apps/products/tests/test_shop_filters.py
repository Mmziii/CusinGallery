from django.urls import reverse

from apps.core.testing import CacheIsolatedAPITestCase
from .helpers import make_attribute, make_attribute_value, make_brand, make_category, make_product, make_variant


class ShopFilterMetadataTests(CacheIsolatedAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.parent = make_category(name="ظروف پخت", slug="cookware")
        cls.child = make_category(parent=cls.parent)
        cls.grandchild = make_category(parent=cls.child)
        cls.brand = make_brand(slug="brand-a")
        cls.cheap = make_product(category=cls.child, brand=cls.brand, name="قابلمه کوچک", price=75000, stock_quantity=3)
        cls.middle = make_product(category=cls.grandchild, brand=cls.brand, name="قابلمه متوسط", price=700000, stock_quantity=3)
        cls.expensive = make_product(category=cls.parent, brand=cls.brand, name="قابلمه بزرگ", price=12000000, stock_quantity=3)
        make_product(category=cls.child, brand=cls.brand, price=1000, stock_quantity=0)
        make_product(category=cls.child, brand=cls.brand, price=25000000, stock_quantity=3, is_active=False)
        cls.other_brand_product = make_product(category=cls.child, brand=make_brand(), price=10, stock_quantity=3)
        make_product(brand=cls.brand, price=90000000, stock_quantity=3)
        material = make_attribute(name="جنس", slug="material")
        steel = make_attribute_value(attribute=material, value="استیل")
        glass = make_attribute_value(attribute=material, value="شیشه")
        make_variant(cls.cheap, attribute_values=[steel])
        make_variant(cls.other_brand_product, attribute_values=[glass])

    def request_products(self, **overrides):
        params = {"category": self.parent.slug, "brand": self.brand.slug, "in_stock": "true"}
        params.update(overrides)
        response = self.client.get(reverse("product-list"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def test_parent_filter_includes_direct_children_and_deeper_descendants(self):
        data = self.request_products()
        self.assertEqual({row["id"] for row in data["results"]}, {self.cheap.pk, self.middle.pk, self.expensive.pk})
        self.assertEqual(data["price_range"], {"min": 75000, "max": 12000000})
        self.assertEqual(data["price_bounds"], data["price_range"])

    def test_result_extrema_include_prices_but_the_handle_domain_can_be_widened(self):
        data = self.request_products(min_price=100000, max_price=1000000)
        self.assertEqual(data["price_range"], {"min": 700000, "max": 700000})
        self.assertEqual(data["price_bounds"], {"min": 75000, "max": 12000000})
        self.assertEqual(data["count"], 1)

    def test_bounds_honor_search_and_dynamic_attributes(self):
        data = self.request_products(search="قابلمه کوچک", attr_material="استیل")
        self.assertEqual(data["price_bounds"], {"min": 75000, "max": 75000})
        self.assertEqual(data["price_range"], data["price_bounds"])

    def test_extrema_cover_all_pages_not_only_the_current_twenty_products(self):
        for index in range(23):
            make_product(category=self.child, brand=self.brand, price=100000 + index, stock_quantity=1)
        data = self.request_products(page=2, ordering="price_asc")
        self.assertEqual(data["count"], 26)
        self.assertEqual(len(data["results"]), 6)
        self.assertEqual(data["price_range"], {"min": 75000, "max": 12000000})

    def test_empty_price_selection_keeps_the_catalog_domain_and_null_result_extrema(self):
        data = self.request_products(min_price=20000000)
        self.assertEqual(data["price_range"], {"min": None, "max": None})
        self.assertEqual(data["price_bounds"], {"min": 75000, "max": 12000000})

    def test_unknown_category_and_empty_search_have_null_bounds(self):
        for overrides in ({"category": "missing"}, {"search": "نامی که وجود ندارد"}):
            data = self.request_products(**overrides)
            self.assertEqual(data["price_range"], {"min": None, "max": None})
            self.assertEqual(data["price_bounds"], {"min": None, "max": None})

    def test_zero_is_a_real_price_not_an_empty_bound(self):
        category = make_category()
        make_product(category=category, brand=self.brand, price=0, stock_quantity=1)
        data = self.request_products(category=category.slug)
        self.assertEqual(data["price_bounds"], {"min": 0, "max": 0})

    def test_facets_use_the_same_category_subtree_and_brand_scope(self):
        response = self.client.get(reverse("product-facets"), {"category": self.parent.slug, "brand": self.brand.slug})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [{"slug": "material", "name": "جنس", "values": [{"value": "استیل", "count": 1}]}])

    def test_on_sale_keeps_only_products_whose_compare_at_price_beats_the_price(self):
        make_product(category=self.child, brand=self.brand, name="کفگیر تخفیف‌دار", price=50000, compare_at_price=90000, stock_quantity=2)
        make_product(category=self.child, brand=self.brand, name="کفگیر معمولی", price=50000, compare_at_price=None, stock_quantity=2)
        # A compare-at price equal to the price is not a discount.
        make_product(category=self.child, brand=self.brand, name="کفگیر بدون تغییر", price=50000, compare_at_price=50000, stock_quantity=2)

        data = self.request_products(category=self.child.slug, brand="", on_sale="true")
        names = {row["name"] for row in data["results"]}
        self.assertIn("کفگیر تخفیف‌دار", names)
        self.assertNotIn("کفگیر معمولی", names)
        self.assertNotIn("کفگیر بدون تغییر", names)

    def test_on_sale_absent_or_falsey_leaves_the_whole_catalog(self):
        data = self.request_products(category=self.child.slug, brand="", on_sale="false")
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(
            {row["name"] for row in self.request_products(category=self.child.slug, brand="")["results"]},
            {row["name"] for row in data["results"]},
        )

    def test_on_sale_accepts_1_true_and_yes_alike(self):
        """«مشاهده همه» links to /shop/?on_sale=1 -- the same set as =true."""
        sale = make_product(
            category=self.child, brand=self.brand, name="پارچ تخفیف‌دار", price=50000, compare_at_price=90000, stock_quantity=2
        )
        plain = make_product(category=self.child, brand=self.brand, name="پارچ معمولی", price=50000, stock_quantity=2)
        sale_ids = {sale.pk}
        for value in ("1", "true", "TRUE", "yes", "on"):
            data = self.request_products(category=self.child.slug, brand="", on_sale=value)
            ids = {row["id"] for row in data["results"]}
            self.assertEqual(ids, sale_ids, f"on_sale={value} should only keep the discounted product")
        self.assertNotIn(plain.pk, sale_ids)

    def test_on_sale_falsey_values_leave_the_catalog_untouched(self):
        sale = make_product(
            category=self.child, brand=self.brand, name="کاسه تخفیف‌دار", price=50000, compare_at_price=90000, stock_quantity=2
        )
        plain = make_product(category=self.child, brand=self.brand, name="کاسه معمولی", price=50000, stock_quantity=2)
        for value in ("0", "false", "FALSE", "no", "off", ""):
            data = self.request_products(category=self.child.slug, brand="", on_sale=value)
            ids = {row["id"] for row in data["results"]}
            self.assertIn(sale.pk, ids, f"on_sale={value!r} must not filter")
            self.assertIn(plain.pk, ids, f"on_sale={value!r} must not filter")

    def test_on_sale_includes_products_with_an_active_daily_deal(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.banners.models import DailyDeal

        now = timezone.now()
        product = make_product(category=self.child, brand=self.brand, name="قوری پیشنهاد روز", price=200000, stock_quantity=2)
        DailyDeal.objects.create(
            product=product, sale_price=150000, starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=2)
        )
        # Same shape, but not active right now -- neither may count.
        expired = make_product(category=self.child, brand=self.brand, name="قوری منقضی", price=200000, stock_quantity=2)
        DailyDeal.objects.create(
            product=expired, sale_price=150000, starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1)
        )
        inactive = make_product(category=self.child, brand=self.brand, name="قوری غیرفعال", price=200000, stock_quantity=2)
        DailyDeal.objects.create(
            product=inactive,
            sale_price=150000,
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
            is_active=False,
        )

        data = self.request_products(category=self.child.slug, brand="", on_sale="1")
        ids = {row["id"] for row in data["results"]}
        self.assertIn(product.pk, ids)
        self.assertNotIn(expired.pk, ids)
        self.assertNotIn(inactive.pk, ids)
