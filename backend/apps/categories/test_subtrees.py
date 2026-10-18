from django.test import TestCase

from apps.categories.models import Category
from apps.categories.tree import category_subtree_ids


class PublicCategorySubtreeTests(TestCase):
    def test_includes_the_selected_parent_and_all_active_descendants(self):
        root = Category.objects.create(name="گروه", slug="group")
        child = Category.objects.create(name="فرزند", slug="child", parent=root)
        grandchild = Category.objects.create(name="نوه", slug="grandchild", parent=child)
        Category.objects.create(name="دیگر", slug="other")
        hidden = Category.objects.create(name="پنهان", slug="hidden", parent=root, is_active=False)
        Category.objects.create(name="زیر پنهان", slug="under-hidden", parent=hidden)
        self.assertEqual(set(category_subtree_ids("GROUP")), {root.pk, child.pk, grandchild.pk})
        self.assertEqual(set(category_subtree_ids("child")), {child.pk, grandchild.pk})

    def test_unknown_and_inactive_categories_have_no_public_subtree(self):
        Category.objects.create(name="پنهان", slug="hidden", is_active=False)
        self.assertEqual(category_subtree_ids("missing"), [])
        self.assertEqual(category_subtree_ids("hidden"), [])

    def test_imported_cycles_terminate_safely(self):
        first = Category.objects.create(name="اول", slug="first")
        second = Category.objects.create(name="دوم", slug="second", parent=first)
        Category.objects.filter(pk=first.pk).update(parent=second)
        self.assertEqual(set(category_subtree_ids("first")), {first.pk, second.pk})
