import importlib

from django.apps import apps
from django.test import TestCase
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
        # (The migrated «آشپزخانه» root is active too, so this is
        # a membership check, not an exact-list check -- see the
        # kitchen-root migration tests below.)
        self.assertIn("Cookware", names)
        self.assertNotIn("Discontinued", names)

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
        # Deliberately NOT slug "kitchen": the 0006 data migration
        # already created the «آشپزخانه» root with that slug in
        # every (migrated) database, and slugs are unique.
        root = make_category("Catalog", slug="catalog")
        child = make_category("Cookware", parent=root)
        make_category("Discontinued Child", parent=root, is_active=False)
        grandchild = make_category("Non-stick Pans", parent=child)

        response = self.client.get(reverse("category-tree"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)

        [root_data] = [c for c in response.data["results"] if c["slug"] == "catalog"]
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
        # Not slug "kitchen": the 0006 migration already created
        # the «آشپزخانه» root with that slug.
        root = make_category("Catalog", slug="catalog")
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


def _kitchen_root_migration():
    # The module name starts with a digit, so it cannot be
    # imported with a regular statement.
    return importlib.import_module(
        "apps.categories.migrations.0006_kitchen_root_category"
    )


class KitchenRootMigrationTests(TestCase):
    """Stage 1: the «آشپزخانه» root data migration (0006).

    The test database is built by running every migration, so
    the root already exists here; tests that need the
    PRE-migration state get it by running the migration's own
    ``backward`` first, then exercising ``forward`` directly.
    """

    def test_forward_creates_root_and_reparents_top_level_categories(self):
        migration = _kitchen_root_migration()
        migration.backward(apps, None)
        pots = make_category("Pots", slug="pots")
        pans = make_category("Pans", slug="pans")
        make_category("Non-stick", slug="non-stick", parent=pots)
        product = make_product(pans, name="Frying pan")

        migration.forward(apps, None)

        kitchen = Category.objects.get(slug="kitchen")
        self.assertEqual(kitchen.name, "آشپزخانه")
        self.assertIsNone(kitchen.parent)
        self.assertTrue(kitchen.is_active)
        pots.refresh_from_db()
        pans.refresh_from_db()
        self.assertEqual(pots.parent, kitchen)
        self.assertEqual(pans.parent, kitchen)
        # Deeper levels keep their parent; products keep their
        # category; slugs (hence every category URL) unchanged.
        self.assertEqual(Category.objects.get(slug="non-stick").parent, pots)
        product.refresh_from_db()
        self.assertEqual(product.category, pans)
        self.assertEqual(
            sorted(Category.objects.filter(parent=kitchen).values_list("slug", flat=True)),
            ["pans", "pots"],
        )

    def test_forward_is_idempotent(self):
        migration = _kitchen_root_migration()
        migration.backward(apps, None)
        make_category("Cookware", slug="cookware")
        migration.forward(apps, None)
        first_pass = list(Category.objects.values_list("slug", "parent__slug"))

        migration.forward(apps, None)  # a second run must change nothing

        self.assertEqual(
            list(Category.objects.values_list("slug", "parent__slug")),
            first_pass,
        )
        self.assertEqual(Category.objects.filter(slug="kitchen").count(), 1)

    def test_forward_is_a_noop_when_the_root_already_exists(self):
        migration = _kitchen_root_migration()
        # Exactly the state after `migrate` has run the migration.
        before = list(Category.objects.values_list("slug", "parent__slug"))
        migration.forward(apps, None)
        self.assertEqual(
            list(Category.objects.values_list("slug", "parent__slug")),
            before,
        )
        self.assertEqual(Category.objects.filter(slug="kitchen").count(), 1)

    def test_forward_uses_fallback_when_kitchen_slug_belongs_to_non_root(self):
        migration = _kitchen_root_migration()
        migration.backward(apps, None)
        archive = make_category("Legacy catalog", slug="legacy-catalog")
        legacy_kitchen = make_category(
            "Legacy kitchen", slug="kitchen", parent=archive
        )
        make_category("Pots", slug="pots")

        migration.forward(apps, None)

        kitchen = Category.objects.get(name="آشپزخانه", parent__isnull=True)
        self.assertEqual(kitchen.slug, "kitchen-root")
        archive.refresh_from_db()
        legacy_kitchen.refresh_from_db()
        self.assertEqual(archive.parent, kitchen)
        self.assertEqual(legacy_kitchen.parent, archive)

        first_pass = list(Category.objects.values_list("slug", "parent__slug"))
        migration.forward(apps, None)
        self.assertEqual(
            list(Category.objects.values_list("slug", "parent__slug")),
            first_pass,
        )
        self.assertEqual(
            Category.objects.filter(name="آشپزخانه", parent__isnull=True).count(),
            1,
        )

        migration.backward(apps, None)
        self.assertFalse(Category.objects.filter(slug="kitchen-root").exists())
        archive.refresh_from_db()
        self.assertIsNone(archive.parent)

    def test_forward_uses_first_available_kitchen_root_suffix(self):
        migration = _kitchen_root_migration()
        migration.backward(apps, None)
        archive = make_category("Legacy catalog", slug="legacy-catalog")
        make_category("Legacy kitchen", slug="kitchen", parent=archive)
        make_category("Reserved kitchen root", slug="kitchen-root", parent=archive)
        make_category("Reserved kitchen root 1", slug="kitchen-root-1", parent=archive)

        migration.forward(apps, None)

        kitchen = Category.objects.get(name="آشپزخانه", parent__isnull=True)
        self.assertEqual(kitchen.slug, "kitchen-root-2")

        migration.forward(apps, None)
        self.assertEqual(
            Category.objects.filter(name="آشپزخانه", parent__isnull=True).count(),
            1,
        )
        self.assertTrue(Category.objects.filter(slug="kitchen-root-2").exists())

    def test_backward_restores_top_level_and_removes_the_root(self):
        migration = _kitchen_root_migration()
        migration.backward(apps, None)
        make_category("Pots", slug="pots")
        migration.forward(apps, None)
        self.assertTrue(Category.objects.filter(parent__slug="kitchen").exists())

        migration.backward(apps, None)

        self.assertFalse(Category.objects.filter(slug="kitchen").exists())
        pots = Category.objects.get(slug="pots")
        self.assertIsNone(pots.parent)

    def test_backward_without_the_root_is_a_noop(self):
        migration = _kitchen_root_migration()
        migration.backward(apps, None)
        migration.backward(apps, None)  # must not raise
        self.assertFalse(Category.objects.filter(slug="kitchen").exists())


class KitchenRootTreeTests(APITestCase):
    """Stage 1: the API tree after the root migration."""

    def test_tree_has_exactly_one_root_the_kitchen(self):
        response = self.client.get(reverse("category-tree"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        roots = response.data["results"]
        self.assertEqual([c["slug"] for c in roots], ["kitchen"])
        self.assertEqual(roots[0]["name"], "آشپزخانه")

    def test_main_groups_are_children_of_the_kitchen_root(self):
        kitchen = Category.objects.get(slug="kitchen")
        group = make_category("قاشق، چنگال و کارد", slug="cutlery", parent=kitchen)
        make_category("قاشق", slug="spoon", parent=group)

        response = self.client.get(reverse("category-tree"))

        [root] = response.data["results"]
        self.assertEqual(root["children"][0]["slug"], "cutlery")
        self.assertEqual(
            root["children"][0]["children"][0]["slug"], "spoon"
        )
