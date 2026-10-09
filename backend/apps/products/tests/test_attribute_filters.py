"""
Part R5 item 8: attribute (facet) filtering + facets endpoint.

Verifies the real HTTP contract of the products API:
  * /products/?attr_<attribute-slug>=value[,value...] narrows to products
    whose ACTIVE variants carry the requested attribute values;
  * unknown attribute slugs / unknown values match nothing (no 500, no 400);
  * /products/facets/ returns attributes + values + counts, scoped by
    ?category=<slug>, and excludes inactive products/variants.
"""
from rest_framework.test import APITestCase

from .helpers import (
    make_attribute,
    make_attribute_value,
    make_category,
    make_product,
    make_variant,
)


class AttributeFilterTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pots = make_category(name="قابلمه", slug="ghablm")
        cls.glass = make_category(name="بلور", slug="bolour")

        color = make_attribute(name="رنگ", slug="rang")
        size = make_attribute(name="سایز", slug="size")
        red = make_attribute_value(attribute=color, value="قرمز")
        blue = make_attribute_value(attribute=color, value="آبی")
        large = make_attribute_value(attribute=size, value="بزرگ")

        cls.p1 = make_product(category=cls.pots, name="قابلمه قرمز")
        make_variant(cls.p1, attribute_values=[red, large])

        # stock_quantity=10 so the existing product-level in_stock filter
        # (Product.stock_quantity) can see it; p3 stays at 0.
        cls.p2 = make_product(category=cls.pots, name="قابلمه آبی", stock_quantity=10)
        make_variant(cls.p2, attribute_values=[blue])

        cls.p3 = make_product(category=cls.glass, name="لیوان آبی")
        make_variant(cls.p3, attribute_values=[blue])

        # Inactive variant must not satisfy the filter.
        cls.p4 = make_product(category=cls.pots, name="قابلمه سبز")
        make_variant(cls.p4, attribute_values=[red], is_active=False)

    def get_slugs(self, response):
        self.assertEqual(response.status_code, 200)
        return {row["slug"] for row in response.json()["results"]}

    def test_single_attribute_value_filters(self):
        slugs = self.get_slugs(self.client.get("/api/v1/products/", {"attr_rang": "قرمز"}))
        self.assertEqual(slugs, {self.p1.slug})

    def test_multiple_values_for_one_attribute_are_ored(self):
        slugs = self.get_slugs(
            self.client.get("/api/v1/products/", {"attr_rang": "قرمز,آبی"})
        )
        self.assertEqual(slugs, {self.p1.slug, self.p2.slug, self.p3.slug})

    def test_attribute_combines_with_category(self):
        slugs = self.get_slugs(
            self.client.get(
                "/api/v1/products/",
                {"attr_rang": "آبی", "category": self.pots.slug},
            )
        )
        self.assertEqual(slugs, {self.p2.slug})

    def test_attribute_combines_with_in_stock(self):
        # p2 has product-level stock, p3 (also آبی) does not -> only p2.
        response = self.client.get(
            "/api/v1/products/", {"attr_rang": "آبی", "in_stock": "true"}
        )
        self.assertEqual(self.get_slugs(response), {self.p2.slug})

    def test_inactive_variant_is_not_matched(self):
        slugs = self.get_slugs(self.client.get("/api/v1/products/", {"attr_rang": "قرمز"}))
        self.assertNotIn(self.p4.slug, slugs)

    def test_unknown_attribute_matches_nothing_without_error(self):
        response = self.client.get("/api/v1/products/", {"attr_nadaram": "چیزی"})
        self.assertEqual(self.get_slugs(response), set())

    def test_known_attribute_unknown_value_matches_nothing(self):
        response = self.client.get("/api/v1/products/", {"attr_rang": "بنفش"})
        self.assertEqual(self.get_slugs(response), set())

    def test_empty_value_is_ignored(self):
        response = self.client.get("/api/v1/products/", {"attr_rang": ""})
        self.assertEqual(len(self.get_slugs(response)), 4)


class FacetsEndpointTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pots = make_category(name="قابلمه", slug="ghablm")
        cls.glass = make_category(name="بلور", slug="bolour")

        color = make_attribute(name="رنگ", slug="rang")
        red = make_attribute_value(attribute=color, value="قرمز")
        blue = make_attribute_value(attribute=color, value="آبی")

        cls.p1 = make_product(category=cls.pots, name="قابلمه قرمز")
        make_variant(cls.p1, attribute_values=[red])

        cls.p2 = make_product(category=cls.pots, name="قابلمه دوم قرمز")
        make_variant(cls.p2, attribute_values=[red])

        cls.p3 = make_product(category=cls.glass, name="لیوان آبی")
        make_variant(cls.p3, attribute_values=[blue])

        cls.p_hidden = make_product(category=cls.pots, name="غیرفعال", is_active=False)
        make_variant(cls.p_hidden, attribute_values=[blue])

    def get_facets(self, params=None):
        response = self.client.get("/api/v1/products/facets/", params or {})
        self.assertEqual(response.status_code, 200)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)
        return response.json()["results"]

    def test_facets_lists_attributes_with_values_and_counts(self):
        facets = self.get_facets()
        self.assertEqual(len(facets), 1)
        color = facets[0]
        self.assertEqual(color["slug"], "rang")
        self.assertEqual(color["name"], "رنگ")
        values = {v["value"]: v["count"] for v in color["values"]}
        # red appears on TWO active products, blue only on the glass one
        # (the inactive product's variant must not count).
        self.assertEqual(values, {"قرمز": 2, "آبی": 1})

    def test_facets_scoped_by_category(self):
        facets = self.get_facets({"category": self.glass.slug})
        self.assertEqual(len(facets), 1)
        values = {v["value"]: v["count"] for v in facets[0]["values"]}
        self.assertEqual(values, {"آبی": 1})

    def test_facets_unknown_category_returns_nothing(self):
        self.assertEqual(self.get_facets({"category": "nope"}), [])
