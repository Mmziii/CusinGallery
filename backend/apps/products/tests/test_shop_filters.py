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
