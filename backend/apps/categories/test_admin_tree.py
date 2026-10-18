"""Task 3: catalog-root flag, tree changelist, leaf-only product form."""
import re

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.categories.models import Category
from apps.products.models import Product

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}

User = get_user_model()
_counter = {"n": 0}


def _make_product(category, name):
    _counter["n"] += 1
    n = _counter["n"]
    return Product.objects.create(
        category=category,
        name=name,
        slug=f"task3-product-{n}",
        sku=f"T3-{n}",
        price=100000,
        stock_quantity=3,
    )


@override_settings(**PLAIN_STATIC)
class CatalogRootFlagTests(TestCase):
    def setUp(self):
        self.root = Category.objects.get(is_catalog_root=True)

    def test_migration_flagged_the_kitchen_root(self):
        self.assertEqual(self.root.slug, "kitchen")
        self.assertIsNone(self.root.parent_id)
        self.assertEqual(Category.objects.filter(is_catalog_root=True).count(), 1)
        self.assertEqual(Category.catalog_root(), self.root)

    def test_second_root_is_rejected(self):
        other = Category(name="ریشهٔ دوم", slug="second-root", is_catalog_root=True)
        with self.assertRaises(ValidationError):
            other.full_clean()

    def test_root_cannot_have_a_parent(self):
        group = Category.objects.create(name="گروه", slug="t3-group", parent=self.root)
        candidate = Category(
            name="ریشهٔ اشتباه", slug="wrong-root",
            parent=group, is_catalog_root=True,
        )
        with self.assertRaises(ValidationError):
            candidate.full_clean()

    def test_category_cannot_become_its_own_ancestor(self):
        group = Category.objects.create(name="پخت‌وپز", slug="t3-cook", parent=self.root)
        leaf = Category.objects.create(name="قابلمه", slug="t3-pot", parent=group)
        group.parent = leaf
        with self.assertRaises(ValidationError):
            group.full_clean()

    def test_full_path_is_root_first(self):
        group = Category.objects.create(name="پخت‌وپز", slug="t3-cook2", parent=self.root)
        leaf = Category.objects.create(name="قابلمه", slug="t3-pot2", parent=group)
        self.assertEqual(leaf.full_path, f"{self.root.name} › پخت‌وپز › قابلمه")
        self.assertTrue(leaf.is_leaf)
        self.assertFalse(group.is_leaf)

    def test_api_exposes_flag_and_rename_keeps_root_findable(self):
        group = Category.objects.create(name="پخت‌وپز", slug="t3-cook3", parent=self.root)
        _make_product(
            Category.objects.create(name="قابلمه", slug="t3-pot3", parent=group),
            "قابلمهٔ آزمایشی",
        )
        # Rename BOTH name and slug: the flag, not the label, is the key.
        self.root.name = "خانه و آشپزخانه"
        self.root.slug = "home-root"
        self.root.save(update_fields=["name", "slug", "updated_at"])
        response = self.client.get(reverse("category-tree"))
        self.assertEqual(response.status_code, 200)
        roots = response.data["results"]
        flagged = [row for row in roots if row["is_catalog_root"]]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["slug"], "home-root")
        flat = self.client.get(reverse("category-list"))
        row = next(r for r in flat.data["results"] if r["slug"] == "home-root")
        self.assertTrue(row["is_catalog_root"])


@override_settings(**PLAIN_STATIC)
class CategoryTreeAdminTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(
            username="tree-owner", password="a-strong-passw0rd!", phone="+989000088001"
        )
        self.client.force_login(self.owner)
        self.root = Category.objects.get(is_catalog_root=True)
        self.group = Category.objects.create(
            name="پخت‌وپز", slug="t3-cooking", parent=self.root, ordering=1
        )
        self.pot = Category.objects.create(
            name="قابلمه", slug="t3-pots", parent=self.group, ordering=1
        )
        self.pan = Category.objects.create(
            name="تابه", slug="t3-pans", parent=self.group, ordering=2,
            is_active=False,
        )
        _make_product(self.pot, "قابلمهٔ یک")
        _make_product(self.pot, "قابلمهٔ دو")
        _make_product(self.pan, "تابهٔ یک")
        self.misplaced = _make_product(self.group, "محصولِ روی والد")

    def _changelist(self):
        return self.client.get(reverse("admin:categories_category_changelist"))

    def test_tree_order_badges_counts_and_subcategory_button(self):
        response = self._changelist()
        self.assertEqual(response.status_code, 200)
        rows = list(response.context["cl"].result_list)
        slugs = [row.slug for row in rows]
        self.assertLess(slugs.index(self.root.slug), slugs.index("t3-cooking"))
        self.assertLess(slugs.index("t3-cooking"), slugs.index("t3-pots"))
        self.assertLess(slugs.index("t3-pots"), slugs.index("t3-pans"))
        by_slug = {row.slug: row for row in rows}
        # Subtree counts: group = 1 direct + 2 pots + 1 pan; root = all 4.
        self.assertEqual(by_slug["t3-cooking"]._subtree_product_count, 4)
        self.assertEqual(by_slug["t3-pots"]._subtree_product_count, 2)
        self.assertEqual(by_slug[self.root.slug]._subtree_product_count, 4)
        body = response.content.decode()
        self.assertIn("└", body)
        self.assertIn("cusin-badge on", body)
        self.assertIn("غیرفعال", body)
        self.assertIn("ریشهٔ کاتالوگ", body)
        self.assertIn("+ زیردسته", body)
        self.assertIn(f"?parent={self.group.pk}", body)
        self.assertIn("data-cusin-modal", body)

    def test_ordering_is_editable_from_the_list(self):
        from django.contrib import admin as dj_admin

        model_admin = dj_admin.site._registry[Category]
        self.assertIn("ordering", model_admin.list_editable)
        response = self._changelist()
        rows = list(response.context["cl"].result_list)
        body = response.content.decode()
        self.assertIn("-ordering", body)
        data = {
            "form-TOTAL_FORMS": str(len(rows)),
            "form-INITIAL_FORMS": str(len(rows)),
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "_save": "ذخیره",
        }
        for i, row in enumerate(rows):
            data[f"form-{i}-id"] = str(row.pk)
            data[f"form-{i}-ordering"] = "9" if row.pk == self.pan.pk else str(row.ordering)
        response = self.client.post(
            reverse("admin:categories_category_changelist"), data
        )
        self.assertEqual(response.status_code, 302)
        self.pan.refresh_from_db()
        self.assertEqual(self.pan.ordering, 9)

    def test_add_subcategory_prefills_parent(self):
        response = self.client.get(
            reverse("admin:categories_category_add"),
            {"parent": self.group.pk},
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        initial_parent = form.initial.get("parent")
        initial_pk = getattr(initial_parent, "pk", initial_parent)
        self.assertEqual(int(initial_pk), self.group.pk)
        # Parent help explains parent vs. leaf in plain Persian.
        help_text = form.fields["parent"].help_text
        self.assertIn("زیرمجموعه", help_text)
        self.assertIn("فقط گروه‌بندی", help_text)

    def test_warning_lists_products_sitting_on_a_parent(self):
        response = self._changelist()
        body = response.content.decode()
        self.assertIn(
            "این محصولات در دستهٔ والد هستند؛ آن‌ها را به یک زیردسته منتقل کنید", body
        )
        self.assertIn("محصولِ روی والد", body)
        names = [
            row["product"].name
            for row in response.context["products_on_parents"]
        ]
        self.assertEqual(names, ["محصولِ روی والد"])


@override_settings(**PLAIN_STATIC)
class LeafOnlyProductFormTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(
            username="leaf-owner", password="a-strong-passw0rd!", phone="+989000088002"
        )
        self.client.force_login(self.owner)
        self.root = Category.objects.get(is_catalog_root=True)
        self.group = Category.objects.create(
            name="پخت‌وپز", slug="t3-leaf-cook", parent=self.root
        )
        self.pot = Category.objects.create(
            name="قابلمه", slug="t3-leaf-pot", parent=self.group
        )

    def _category_labels(self, response):
        field = response.context["adminform"].form.fields["category"]
        labels = [str(label) for _value, label in field.choices if _value]
        return field, labels

    def test_add_form_offers_only_leaves_with_full_paths(self):
        response = self.client.get(reverse("admin:products_product_add"))
        field, labels = self._category_labels(response)
        self.assertIn(f"{self.root.name} › پخت‌وپز › قابلمه", labels)
        self.assertNotIn(f"{self.root.name} › پخت‌وپز", labels)
        self.assertNotIn(self.root.name, labels)
        self.assertIn(
            "محصول را فقط در زیردسته‌ها قرار دهید؛ دسته‌های والد فقط گروه‌بندی هستند.",
            field.help_text,
        )

    def test_legacy_product_on_parent_stays_editable_with_warning(self):
        legacy = _make_product(self.group, "کالای قدیمی")
        response = self.client.get(
            reverse("admin:products_product_change", args=[legacy.pk])
        )
        field, labels = self._category_labels(response)
        # Its current (parent) category is present so the form is valid,
        # and the help tells the owner to move it.
        self.assertIn(f"{self.root.name} › پخت‌وپز", labels)
        self.assertIn("به یک زیردسته منتقل کنید", field.help_text)

    def test_move_to_category_action_moves_and_rejects_parent_target(self):
        legacy = _make_product(self.group, "کالای روی والد")
        response = self.client.post(
            reverse("admin:products_product_changelist"),
            {
                "action": "move_to_category",
                ACTION_CHECKBOX_NAME: [legacy.pk],
                "index": 0,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("انتقال به دسته…", body)
        self.assertIn(f"{self.root.name} › پخت‌وپز › قابلمه", body)

        # A parent category as target is refused server-side.
        response = self.client.post(
            reverse("admin:products_product_move_to_category"),
            {"ids": str(legacy.pk), "category": str(self.group.pk)},
            follow=True,
        )
        legacy.refresh_from_db()
        self.assertEqual(legacy.category_id, self.group.pk)
        self.assertIn("دستهٔ والد است", response.content.decode())

        response = self.client.post(
            reverse("admin:products_product_move_to_category"),
            {"ids": str(legacy.pk), "category": str(self.pot.pk)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        legacy.refresh_from_db()
        self.assertEqual(legacy.category_id, self.pot.pk)
        self.assertIn("منتقل شد", response.content.decode())
