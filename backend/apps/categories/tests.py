from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.products.models import Product

from .models import Category


def make_category(name, **overrides):
    defaults = {"slug": name.lower().replace(" ", "-")}
    defaults.update(overrides)
    return Category.objects.create(name=name, **defaults)


def make_product(category, name="Pot", **overrides):
    defaults = {
        "slug": name.lower().replace(" ", "-") + "-" + str(category.pk),
        "sku": f"SKU-{name}-{category.pk}",
        "price": 100000,
    }
    defaults.update(overrides)
    return Product.objects.create(category=category, name=name, **defaults)


class CategoryListDetailTests(APITestCase):
    def test_list_returns_only_active_categories(self):
        make_category("Cookware", is_active=True)
        make_category("Discontinued", is_active=False)

        response = self.client.get(reverse("category-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [c["name"] for c in response.data["results"]]
        self.assertEqual(names, ["Cookware"])

    def test_detail_lookup_by_slug(self):
        category = make_category("Glassware")
        response = self.client.get(reverse("category-detail", args=["glassware"]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], category.id)
        self.assertEqual(response.data["name"], "Glassware")

    def test_top_level_category_has_null_parent_slug_without_error(self):
        """Regression guard: a naive SlugField(source="parent.slug")
        would crash on exactly this, the common case (most categories
        are top-level) -- see CategorySerializer.get_parent_slug's
        docstring."""
        make_category("Root Category")
        response = self.client.get(reverse("category-list"))
        row = next(c for c in response.data["results"] if c["slug"] == "root-category")
        self.assertIsNone(row["parent_slug"])
        self.assertIsNone(row["parent"])

    def test_child_category_reports_parent_slug(self):
        root = make_category("Parent Cat", slug="parent-cat")
        make_category("Child Cat", slug="child-cat", parent=root)
        response = self.client.get(reverse("category-detail", args=["child-cat"]))
        self.assertEqual(response.data["parent_slug"], "parent-cat")
        self.assertEqual(response.data["parent"], root.id)

    def test_inactive_category_detail_is_not_found(self):
        make_category("Hidden", is_active=False)
        response = self.client.get(reverse("category-detail", args=["hidden"]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_count_only_counts_active_products(self):
        category = make_category("Pans")
        make_product(category, name="Pan A", is_active=True)
        make_product(category, name="Pan B", is_active=True)
        make_product(category, name="Pan C", is_active=False)

        response = self.client.get(reverse("category-detail", args=["pans"]))
        self.assertEqual(response.data["product_count"], 2)

    def test_write_methods_are_not_allowed(self):
        """No create/update/delete endpoint exists at all -- catalog data
        is admin-managed only (ReadOnlyModelViewSet)."""
        category = make_category("Locked")
        list_url = reverse("category-list")
        detail_url = reverse("category-detail", args=["locked"])

        self.assertEqual(
            self.client.post(list_url, {"name": "New", "slug": "new"}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(detail_url, {"name": "Changed"}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(self.client.delete(detail_url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        category.refresh_from_db()
        self.assertEqual(category.name, "Locked")


class CategoryTreeTests(APITestCase):
    def test_tree_returns_nested_active_children_only(self):
        root = make_category("Kitchen")
        child = make_category("Cookware", parent=root)
        make_category("Discontinued Child", parent=root, is_active=False)
        grandchild = make_category("Non-stick Pans", parent=child)

        response = self.client.get(reverse("category-tree"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)

        [root_data] = [c for c in response.data["results"] if c["slug"] == "kitchen"]
        self.assertEqual(len(root_data["children"]), 1)
        self.assertEqual(root_data["children"][0]["slug"], "cookware")
        self.assertEqual(root_data["children"][0]["children"][0]["slug"], "non-stick-pans")

    def test_tree_excludes_inactive_roots(self):
        make_category("Hidden Root", is_active=False)
        response = self.client.get(reverse("category-tree"))
        slugs = [c["slug"] for c in response.data["results"]]
        self.assertNotIn("hidden-root", slugs)

    def test_tree_query_count_is_bounded_not_per_node(self):
        """Regression guard for N+1: the number of queries should scale
        with tree DEPTH (bounded, see views.TREE_PREFETCH_DEPTH), not
        with the number of nodes at any given level.

        Measured as a width-comparison (same methodology as the
        products/cart performance tests) rather than one pinned literal:
        Django skips prefetch-level queries once a level returns no rows,
        so the exact count for a given tree is 1 (roots) + one query per
        level actually traversed -- a literal "always 5" would be wrong
        for every tree shallower than TREE_PREFETCH_DEPTH.
        """
        root = make_category("Kitchen")
        for i in range(10):
            make_category(f"Child {i}", parent=root)

        small_count = self._tree_query_count()

        # Triple the width at the same depth -- if queries grow, the
        # endpoint is fanning out per node.
        for i in range(10, 30):
            make_category(f"Child {i}", parent=root)
        large_count = self._tree_query_count()

        self.assertEqual(
            small_count,
            large_count,
            f"Tree query count grew with node count ({small_count} -> {large_count}) -- "
            "likely an N+1 in CategoryViewSet.tree.",
        )

    def test_tree_query_count_is_bounded_by_depth_cap(self):
        """A chain deeper than TREE_PREFETCH_DEPTH must still cost a
        bounded number of queries: the paginator's root count plus the
        root query, then at most one query per prefetch level
        (views.TREE_PREFETCH_DEPTH)."""
        from apps.categories.views import TREE_PREFETCH_DEPTH

        node = make_category("Deep Root")
        for i in range(TREE_PREFETCH_DEPTH + 2):  # deeper than the cap
            node = make_category(f"Level {i}", parent=node)

        count = self._tree_query_count()
        self.assertLessEqual(count, 2 + TREE_PREFETCH_DEPTH)

    def _tree_query_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("category-tree"))
            assert response.status_code == status.HTTP_200_OK, response.content
        return len(ctx.captured_queries)
