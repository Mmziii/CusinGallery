from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from .helpers import make_brand, make_category, make_product


class ProductListVisibilityTests(CacheIsolatedAPITestCase):
    def test_inactive_products_are_excluded(self):
        make_product(name="Visible", is_active=True)
        make_product(name="Hidden", is_active=False)

        response = self.client.get(reverse("product-list"))
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Visible"])

    def test_products_in_inactive_category_still_appear(self):
        """The product's OWN is_active flag governs visibility, not its
        category's -- an inactive category is a separate, independent
        concern (see CategoryViewSet) that this app doesn't need to
        cross-check, since the master spec only asks to exclude inactive
        *categories* from the category endpoints, not to cascade that
        into hiding otherwise-active products."""
        category = make_category(is_active=False)
        make_product(category=category, name="Still Listed", is_active=True)
        response = self.client.get(reverse("product-list"))
        names = [p["name"] for p in response.data["results"]]
        self.assertIn("Still Listed", names)


class ProductFilterTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.url = reverse("product-list")
        self.cookware = make_category(name="Cookware", slug="cookware")
        self.glassware = make_category(name="Glassware", slug="glassware")
        self.brand_a = make_brand(name="Brand A", slug="brand-a")
        self.brand_b = make_brand(name="Brand B", slug="brand-b")

    def test_filter_by_category_slug(self):
        make_product(category=self.cookware, name="Pot")
        make_product(category=self.glassware, name="Glass")

        response = self.client.get(self.url, {"category": "cookware"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Pot"])

    def test_filter_by_brand_slug(self):
        make_product(brand=self.brand_a, name="From A")
        make_product(brand=self.brand_b, name="From B")

        response = self.client.get(self.url, {"brand": "brand-a"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["From A"])

    def test_filter_by_min_price(self):
        make_product(name="Cheap", price=50000)
        make_product(name="Expensive", price=500000)

        response = self.client.get(self.url, {"min_price": 100000})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Expensive"])

    def test_filter_by_max_price(self):
        make_product(name="Cheap", price=50000)
        make_product(name="Expensive", price=500000)

        response = self.client.get(self.url, {"max_price": 100000})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Cheap"])

    def test_filter_by_price_range(self):
        make_product(name="Too Cheap", price=10000)
        make_product(name="Just Right", price=150000)
        make_product(name="Too Expensive", price=900000)

        response = self.client.get(self.url, {"min_price": 100000, "max_price": 200000})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Just Right"])

    def test_filter_by_availability_in_stock(self):
        make_product(name="Available", stock_quantity=5)
        make_product(name="Sold Out", stock_quantity=0)

        response = self.client.get(self.url, {"in_stock": "true"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Available"])

    def test_filter_by_availability_out_of_stock(self):
        make_product(name="Available", stock_quantity=5)
        make_product(name="Sold Out", stock_quantity=0)

        response = self.client.get(self.url, {"in_stock": "false"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Sold Out"])

    def test_combined_filters(self):
        make_product(category=self.cookware, brand=self.brand_a, name="Match", price=120000)
        make_product(category=self.cookware, brand=self.brand_b, name="Wrong Brand", price=120000)
        make_product(category=self.glassware, brand=self.brand_a, name="Wrong Category", price=120000)

        response = self.client.get(
            self.url, {"category": "cookware", "brand": "brand-a", "min_price": 100000}
        )
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Match"])


class ProductSortingTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.url = reverse("product-list")

    def test_default_ordering_is_newest_first(self):
        first = make_product(name="First")
        second = make_product(name="Second")
        response = self.client.get(self.url)
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Second", "First"])

    def test_price_ascending(self):
        make_product(name="Mid", price=200000)
        make_product(name="Low", price=50000)
        make_product(name="High", price=900000)

        response = self.client.get(self.url, {"ordering": "price_asc"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Low", "Mid", "High"])

    def test_price_descending(self):
        make_product(name="Mid", price=200000)
        make_product(name="Low", price=50000)
        make_product(name="High", price=900000)

        response = self.client.get(self.url, {"ordering": "price_desc"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["High", "Mid", "Low"])

    def test_invalid_ordering_value_is_rejected(self):
        response = self.client.get(self.url, {"ordering": "popularity"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ordering", response.data)


class ProductSearchTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.url = reverse("product-list")

    def test_search_matches_product_name(self):
        make_product(name="Stainless Steel Pot")
        make_product(name="Glass Vase")

        response = self.client.get(self.url, {"search": "Steel"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Stainless Steel Pot"])

    def test_search_matches_sku(self):
        make_product(name="Widget", sku="UNIQUE-SKU-123")
        make_product(name="Other Widget", sku="DIFFERENT-456")

        response = self.client.get(self.url, {"search": "UNIQUE-SKU-123"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Widget"])

    def test_search_matches_brand_name(self):
        brand = make_brand(name="SearchableBrand")
        make_product(name="Branded Item", brand=brand)
        make_product(name="Unbranded Item")

        response = self.client.get(self.url, {"search": "SearchableBrand"})
        names = [p["name"] for p in response.data["results"]]
        self.assertEqual(names, ["Branded Item"])

    def test_search_with_no_matches_returns_empty_list(self):
        make_product(name="Something")
        response = self.client.get(self.url, {"search": "NoSuchThingExists"})
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])


class ProductPaginationTests(CacheIsolatedAPITestCase):
    def test_pagination_metadata_shape(self):
        for i in range(3):
            make_product(name=f"Product {i}")

        response = self.client.get(reverse("product-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)
        self.assertEqual(response.data["count"], 3)

    def test_pagination_actually_limits_page_size(self):
        # PAGE_SIZE is 20 (see config/settings/base.py) -- create more
        # than that and confirm the response is genuinely paginated, not
        # just carrying pagination-shaped metadata around a full dump.
        for i in range(25):
            make_product(name=f"Product {i}")

        response = self.client.get(reverse("product-list"))
        self.assertEqual(len(response.data["results"]), 20)
        self.assertEqual(response.data["count"], 25)
        self.assertIsNotNone(response.data["next"])

    def test_pagination_works_together_with_filtering_and_sorting(self):
        category = make_category(slug="paged-category")
        for i in range(25):
            make_product(category=category, name=f"Item {i}", price=1000 * (i + 1))

        response = self.client.get(
            reverse("product-list"),
            {"category": "paged-category", "ordering": "price_desc", "page": 2},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)  # 25 total, page 2 of size 20
