"""B7: create_staff_groups management command -- idempotency, exact
permission sets, no deletes, membership preserved, and the groups really
scoping admin access."""
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.adminui.management.commands.create_staff_groups import STAFF_GROUPS

from .helpers import PLAIN_STATIC, make_staff


def perm_set(group):
    return set(
        group.permissions.values_list("content_type__app_label", "codename")
    )


@override_settings(**PLAIN_STATIC)
class StaffGroupsCommandTests(TestCase):
    maxDiff = None

    def test_command_creates_three_groups_with_exact_permissions(self):
        call_command("create_staff_groups")
        self.assertEqual(Group.objects.count(), 3)
        for name, wanted in STAFF_GROUPS.items():
            with self.subTest(group=name):
                group = Group.objects.get(name=name)
                self.assertEqual(perm_set(group), set(wanted))

    def test_idempotent_second_run_refreshes_without_duplicating(self):
        call_command("create_staff_groups")
        first = {g.name: perm_set(g) for g in Group.objects.all()}
        call_command("create_staff_groups")
        self.assertEqual(Group.objects.count(), 3)
        second = {g.name: perm_set(g) for g in Group.objects.all()}
        self.assertEqual(first, second)

    def test_second_run_repairs_tampered_permissions(self):
        call_command("create_staff_groups")
        group = Group.objects.get(name="انباردار")
        from django.contrib.auth.models import Permission

        extra = Permission.objects.get(
            content_type__app_label="orders", codename="change_order"
        )
        group.permissions.add(extra)
        call_command("create_staff_groups")
        self.assertNotIn(("orders", "change_order"), perm_set(group))

    def test_membership_is_preserved(self):
        user = make_staff(username="+989000060001", phone="+989000060001")
        call_command("create_staff_groups")
        user.groups.add(Group.objects.get(name="اپراتور سفارش"))
        call_command("create_staff_groups")
        user.refresh_from_db()
        self.assertEqual(
            list(user.groups.values_list("name", flat=True)),
            ["اپراتور سفارش"],
        )

    def test_no_group_grants_any_delete_permission(self):
        call_command("create_staff_groups")
        for group in Group.objects.all():
            with self.subTest(group=group.name):
                codenames = set(group.permissions.values_list("codename", flat=True))
                self.assertFalse(
                    any(c.startswith("delete_") for c in codenames),
                    f"{group.name} grants delete permissions",
                )


@override_settings(**PLAIN_STATIC)
class StaffGroupsAccessTests(TestCase):
    """The groups must actually scope what a member sees in the admin."""

    def setUp(self):
        call_command("create_staff_groups")

    def test_order_operator_scope(self):
        user = make_staff(username="+989000060002", phone="+989000060002")
        user.groups.add(Group.objects.get(name="اپراتور سفارش"))
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(reverse("admin:orders_order_changelist")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("admin:products_product_changelist")).status_code,
            200,  # view-only
        )
        # ...but cannot change products
        self.assertFalse(user.has_perm("products.change_product"))
        self.assertTrue(user.has_perm("orders.change_order"))
        self.assertFalse(user.has_perm("orders.delete_order"))
        # the admin index only lists apps they may see
        index = self.client.get(reverse("admin:index"))
        self.assertEqual(index.status_code, 200)

    def test_warehouse_scope(self):
        user = make_staff(username="+989000060003", phone="+989000060003")
        user.groups.add(Group.objects.get(name="انباردار"))
        self.client.force_login(user)
        self.assertTrue(user.has_perm("products.change_product"))
        self.assertFalse(user.has_perm("orders.change_order"))
        self.assertEqual(
            self.client.get(reverse("admin:products_product_changelist")).status_code,
            200,
        )

    def test_content_scope(self):
        user = make_staff(username="+989000060004", phone="+989000060004")
        user.groups.add(Group.objects.get(name="محتوا و بازاریابی"))
        self.client.force_login(user)
        self.assertTrue(user.has_perm("banners.change_banner"))
        self.assertTrue(user.has_perm("reviews.change_review"))
        self.assertFalse(user.has_perm("orders.view_order"))
        self.assertEqual(
            self.client.get(reverse("admin:banners_banner_changelist")).status_code,
            200,
        )
        # orders admin is off limits
        response = self.client.get(reverse("admin:orders_order_changelist"))
        self.assertEqual(response.status_code, 403)
