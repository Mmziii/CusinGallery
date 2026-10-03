from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from .helpers import (
    make_attribute,
    make_attribute_value,
    make_brand,
    make_category,
    make_image,
    make_product,
    make_variant,
)


class ProductDetailBasicTests(CacheIsolatedAPITestCase):
    def test_detail_lookup_by_slug(self):
        category = make_category(name="Cookware")
        brand = make_brand(name="Persia Steel")
        product = make_product(
            category=category, brand=brand, name="Copper Pot", slug="copper-pot",
            description="A fine copper pot.", short_description="Copper pot",
        )
        response = self.client.get(reverse("product-detail", args=["copper-pot"]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], product.id)
        self.assertEqual(response.data["name"], "Copper Pot")
        self.assertEqual(response.data["description"], "A fine copper pot.")
        self.assertEqual(response.data["category"]["slug"], category.slug)
        self.assertEqual(response.data["brand"]["slug"], brand.slug)

    def test_inactive_product_detail_is_not_found(self):
        make_product(name="Hidden", slug="hidden-product", is_active=False)
        response = self.client.get(reverse("product-detail", args=["hidden-product"]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_slug_is_not_found(self):
        response = self.client.get(reverse("product-detail", args=["does-not-exist"]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_includes_fields_absent_from_list(self):
        """description/sku/images/variants/specifications/related_products
        are detail-only -- see ProductDetailSerializer's docstring on why
        the list serializer deliberately omits them."""
        make_product(name="Full Detail", slug="full-detail", sku="SKU-FD-1")
        response = self.client.get(reverse("product-detail", args=["full-detail"]))
        for field in ("description", "sku", "images", "variants", "specifications", "related_products"):
            self.assertIn(field, response.data)

    def test_list_does_not_include_detail_only_fields(self):
        make_product(name="Lean", slug="lean")
        response = self.client.get(reverse("product-list"))
        row = response.data["results"][0]
        for field in ("description", "sku", "images", "variants", "specifications", "related_products"):
            self.assertNotIn(field, row)


class ProductPricingTests(CacheIsolatedAPITestCase):
    def test_price_info_without_sale(self):
        product = make_product(name="Plain", slug="plain", price=150000)
        response = self.client.get(reverse("product-detail", args=["plain"]))
        info = response.data["price_info"]
        self.assertEqual(info["price"], 150000)
        self.assertIsNone(info["compare_at_price"])
        self.assertFalse(info["is_on_sale"])
        self.assertEqual(info["discount_amount"], 0)

    def test_price_info_with_valid_sale(self):
        make_product(
            name="On Sale", slug="on-sale", price=80000, compare_at_price=100000, discount_percentage=20,
        )
        response = self.client.get(reverse("product-detail", args=["on-sale"]))
        info = response.data["price_info"]
        self.assertEqual(info["price"], 80000)
        self.assertEqual(info["compare_at_price"], 100000)
        self.assertTrue(info["is_on_sale"])
        self.assertEqual(info["discount_amount"], 20000)
        self.assertEqual(info["discount_percentage"], 20)

    def test_discount_percentage_and_compare_at_price_are_independent_signals(self):
        """A product can have a discount_percentage badge set without any
        compare_at_price -- these are deliberately independent (see
        apps/products/pricing.py's module docstring), not derived from
        each other."""
        make_product(name="Badge Only", slug="badge-only", price=100000, discount_percentage=15)
        response = self.client.get(reverse("product-detail", args=["badge-only"]))
        info = response.data["price_info"]
        self.assertEqual(info["discount_percentage"], 15)
        self.assertFalse(info["is_on_sale"])
        self.assertIsNone(info["compare_at_price"])

    def test_variant_with_own_price_shows_no_inherited_discount(self):
        product = make_product(
            name="Has Variants", slug="has-variants", price=100000, compare_at_price=120000,
        )
        variant = make_variant(product, price=90000)
        response = self.client.get(reverse("product-detail", args=["has-variants"]))
        variant_data = next(v for v in response.data["variants"] if v["id"] == variant.id)
        self.assertEqual(variant_data["price_info"]["price"], 90000)
        self.assertIsNone(variant_data["price_info"]["compare_at_price"])
        self.assertFalse(variant_data["price_info"]["is_on_sale"])

    def test_variant_without_own_price_inherits_product_sale_info(self):
        product = make_product(
            name="Inherits Sale", slug="inherits-sale", price=80000, compare_at_price=100000,
        )
        variant = make_variant(product, price=None)
        response = self.client.get(reverse("product-detail", args=["inherits-sale"]))
        variant_data = next(v for v in response.data["variants"] if v["id"] == variant.id)
        self.assertEqual(variant_data["price_info"]["price"], 80000)
        self.assertEqual(variant_data["price_info"]["compare_at_price"], 100000)
        self.assertTrue(variant_data["price_info"]["is_on_sale"])


class ProductStockStatusTests(CacheIsolatedAPITestCase):
    def test_out_of_stock_status(self):
        make_product(name="None Left", slug="none-left", stock_quantity=0)
        response = self.client.get(reverse("product-detail", args=["none-left"]))
        self.assertEqual(response.data["stock_status"], "out_of_stock")
        self.assertFalse(response.data["is_in_stock"])

    def test_low_stock_status(self):
        make_product(name="Almost Gone", slug="almost-gone", stock_quantity=2, low_stock_threshold=5)
        response = self.client.get(reverse("product-detail", args=["almost-gone"]))
        self.assertEqual(response.data["stock_status"], "low_stock")
        self.assertTrue(response.data["is_in_stock"])

    def test_in_stock_status(self):
        make_product(name="Plenty", slug="plenty", stock_quantity=50, low_stock_threshold=5)
        response = self.client.get(reverse("product-detail", args=["plenty"]))
        self.assertEqual(response.data["stock_status"], "in_stock")

    def test_exact_stock_quantity_is_never_exposed(self):
        """Coarse status only -- see pricing.stock_status_for's docstring."""
        category = make_category(name="Secret Category", slug="secret-category")
        make_product(
            category=category, name="Secretive", slug="secretive", sku="SKU-SECRETIVE",
            stock_quantity=42, low_stock_threshold=5,
        )
        response = self.client.get(reverse("product-detail", args=["secretive"]))
        self.assertNotIn("stock_quantity", response.data)
        self.assertNotIn("low_stock_threshold", response.data)

        # Substring-scan the serialized body for the exact stock count,
        # with auto-incremented identifier values stripped first. (The
        # previous raw scan of the whole body was flaky: it also matched
        # generated ids that happened to contain the same digits, e.g.
        # category id 424, making the test depend on where other test
        # modules had left the database sequences. With deterministic
        # fixture values and ids excluded, "42" can now only appear if
        # the stock itself leaked.)
        def without_ids(node):
            if isinstance(node, dict):
                return {
                    key: without_ids(value)
                    for key, value in node.items()
                    if key != "id" and not key.endswith("_id")
                }
            if isinstance(node, list):
                return [without_ids(value) for value in node]
            return node

        self.assertNotIn("42", str(without_ids(response.data)))


class ProductImageTests(CacheIsolatedAPITestCase):
    def test_primary_image_is_returned_first_in_list_view(self):
        product = make_product(name="Multi Image", slug="multi-image")
        make_image(product, image="products/secondary.jpg", is_primary=False, ordering=1)
        primary = make_image(product, image="products/primary.jpg", is_primary=True, ordering=2)

        response = self.client.get(reverse("product-list"))
        row = next(p for p in response.data["results"] if p["slug"] == "multi-image")
        self.assertEqual(row["primary_image"]["id"], primary.id)
        self.assertTrue(row["primary_image"]["is_primary"])

    def test_product_with_no_images_has_null_primary_image(self):
        make_product(name="No Image", slug="no-image")
        response = self.client.get(reverse("product-list"))
        row = next(p for p in response.data["results"] if p["slug"] == "no-image")
        self.assertIsNone(row["primary_image"])

    def test_detail_includes_all_images_ordered(self):
        product = make_product(name="Gallery", slug="gallery")
        make_image(product, image="products/third.jpg", ordering=3, is_primary=False)
        make_image(product, image="products/first.jpg", ordering=1, is_primary=False)
        make_image(product, image="products/second.jpg", ordering=2, is_primary=False)

        response = self.client.get(reverse("product-detail", args=["gallery"]))
        orderings = [img["ordering"] for img in response.data["images"]]
        self.assertEqual(orderings, sorted(orderings))


class ProductAttributesAndSpecificationsTests(CacheIsolatedAPITestCase):
    def test_specifications_are_grouped_by_attribute_with_deduped_values(self):
        product = make_product(name="Specced", slug="specced")
        material = make_attribute(name="Material")
        steel = make_attribute_value(attribute=material, value="Steel")
        copper = make_attribute_value(attribute=material, value="Copper")

        make_variant(product, attribute_values=[steel])
        make_variant(product, attribute_values=[copper])
        make_variant(product, attribute_values=[steel])  # duplicate value, different variant

        response = self.client.get(reverse("product-detail", args=["specced"]))
        specs = response.data["specifications"]
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["attribute"], "Material")
        self.assertEqual(sorted(specs[0]["values"]), ["Copper", "Steel"])

    def test_product_with_no_variants_has_empty_specifications(self):
        make_product(name="Simple", slug="simple")
        response = self.client.get(reverse("product-detail", args=["simple"]))
        self.assertEqual(response.data["specifications"], [])

    def test_inactive_variant_does_not_contribute_to_specifications(self):
        product = make_product(name="Partially Hidden", slug="partially-hidden")
        color = make_attribute(name="Color")
        red = make_attribute_value(attribute=color, value="Red")
        make_variant(product, attribute_values=[red], is_active=False)

        response = self.client.get(reverse("product-detail", args=["partially-hidden"]))
        self.assertEqual(response.data["specifications"], [])


class ProductVariantTests(CacheIsolatedAPITestCase):
    def test_inactive_variants_are_excluded_from_detail(self):
        product = make_product(name="Has Hidden Variant", slug="has-hidden-variant")
        active = make_variant(product, sku="ACTIVE-SKU", is_active=True)
        make_variant(product, sku="HIDDEN-SKU", is_active=False)

        response = self.client.get(reverse("product-detail", args=["has-hidden-variant"]))
        variant_ids = [v["id"] for v in response.data["variants"]]
        self.assertEqual(variant_ids, [active.id])

    def test_out_of_stock_variant_is_still_shown_but_flagged(self):
        """An out-of-stock (but active) variant must still appear in the
        response -- the frontend needs it present (to show as disabled),
        just correctly flagged as unavailable. See master spec section 8:
        "unavailable variants cannot accidentally be selected"."""
        product = make_product(name="Mixed Stock", slug="mixed-stock")
        variant = make_variant(product, sku="OOS-SKU", stock_quantity=0)

        response = self.client.get(reverse("product-detail", args=["mixed-stock"]))
        variant_data = next(v for v in response.data["variants"] if v["id"] == variant.id)
        self.assertFalse(variant_data["is_in_stock"])
        self.assertEqual(variant_data["stock_status"], "out_of_stock")

    def test_variant_includes_its_attribute_values(self):
        product = make_product(name="Colorful", slug="colorful")
        color = make_attribute(name="Color")
        red = make_attribute_value(attribute=color, value="Red")
        variant = make_variant(product, attribute_values=[red])

        response = self.client.get(reverse("product-detail", args=["colorful"]))
        variant_data = next(v for v in response.data["variants"] if v["id"] == variant.id)
        self.assertEqual(len(variant_data["attribute_values"]), 1)
        self.assertEqual(variant_data["attribute_values"][0]["value"], "Red")
        self.assertEqual(variant_data["attribute_values"][0]["attribute"], "Color")


class RelatedProductsTests(CacheIsolatedAPITestCase):
    def test_related_products_are_same_category_excluding_self(self):
        category = make_category(name="Related Category")
        main = make_product(category=category, name="Main", slug="main-product")
        sibling = make_product(category=category, name="Sibling", slug="sibling-product")
        other_category_product = make_product(name="Elsewhere", slug="elsewhere")

        response = self.client.get(reverse("product-detail", args=["main-product"]))
        related_ids = [p["id"] for p in response.data["related_products"]]

        self.assertIn(sibling.id, related_ids)
        self.assertNotIn(main.id, related_ids)
        self.assertNotIn(other_category_product.id, related_ids)

    def test_related_products_excludes_inactive_products(self):
        category = make_category(name="Cat")
        main = make_product(category=category, name="Main2", slug="main-product-2")
        make_product(category=category, name="Inactive Sibling", slug="inactive-sibling", is_active=False)

        response = self.client.get(reverse("product-detail", args=["main-product-2"]))
        names = [p["name"] for p in response.data["related_products"]]
        self.assertNotIn("Inactive Sibling", names)

    def test_related_products_capped_at_six(self):
        category = make_category(name="Big Category")
        main = make_product(category=category, name="Main3", slug="main-product-3")
        for i in range(10):
            make_product(category=category, name=f"Related {i}", slug=f"related-{i}")

        response = self.client.get(reverse("product-detail", args=["main-product-3"]))
        self.assertLessEqual(len(response.data["related_products"]), 6)
