"""Idempotent staff permission groups for the shop owner (B7).

    python manage.py create_staff_groups

Creates (or refreshes) three Django auth groups with Persian names so the
owner can hand out scoped admin access without touching individual
permissions:

* «اپراتور سفارش» -- answers the phone: sees and moves orders, reads
  products and customers. No deletes, no prices, no settings.
* «انباردار» -- stock and prices: edits products (and their variants),
  reads orders. No deletes.
* «محتوا و بازاریابی» -- storefront content: banners, daily deals,
  coupons, review moderation, read-only site settings.

Running the command again only re-applies the permission sets (groups and
their members are untouched), so it is safe in deploys and tests. Documented
in docs/OWNER_GUIDE.fa.md (section «گروه‌های دسترسی کارکنان»).
"""
from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

# group name -> list of (app_label, codename)
STAFF_GROUPS: dict[str, list[tuple[str, str]]] = {
    "اپراتور سفارش": [
        ("orders", "view_order"),
        ("orders", "change_order"),
        ("orders", "view_orderitem"),
        # Read-only product/customer context while handling an order.
        ("products", "view_product"),
        ("products", "view_productvariant"),
        ("products", "view_productimage"),
        ("accounts", "view_user"),
        ("accounts", "view_address"),
    ],
    "انباردار": [
        ("products", "view_product"),
        ("products", "change_product"),
        ("products", "view_productvariant"),
        ("products", "change_productvariant"),
        ("products", "view_productimage"),
        # Read orders to match shipments against stock moves.
        ("orders", "view_order"),
        ("orders", "view_orderitem"),
    ],
    "محتوا و بازاریابی": [
        ("banners", "view_banner"),
        ("banners", "add_banner"),
        ("banners", "change_banner"),
        ("banners", "view_dailydeal"),
        ("banners", "add_dailydeal"),
        ("banners", "change_dailydeal"),
        ("discounts", "view_coupon"),
        ("discounts", "add_coupon"),
        ("discounts", "change_coupon"),
        ("discounts", "view_couponusage"),
        ("reviews", "view_review"),
        ("reviews", "change_review"),
        ("core", "view_sitesettings"),
    ],
}

# Codenames that must NEVER appear in any staff group (defensive guard:
# the spec says no deletes for scoped roles).
FORBIDDEN_PREFIXES = ("delete_",)


class Command(BaseCommand):
    help = (
        "Create/refresh the three scoped staff groups (اپراتور سفارش، "
        "انباردار، محتوا و بازاریابی). Idempotent; never deletes groups."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        perm_cache: dict[tuple[str, str], Permission] = {}

        def perm(app_label: str, codename: str) -> Permission:
            key = (app_label, codename)
            if key not in perm_cache:
                perm_cache[key] = Permission.objects.get(
                    content_type__app_label=app_label, codename=codename,
                )
            return perm_cache[key]

        for group_name, wanted in STAFF_GROUPS.items():
            for _app, codename in wanted:
                if codename.startswith(FORBIDDEN_PREFIXES):
                    raise RuntimeError(
                        f"Programming error: {codename!r} must not be granted "
                        f"to staff group {group_name!r}."
                    )
            group, created = Group.objects.get_or_create(name=group_name)
            permissions = [perm(app, code) for app, code in wanted]
            group.permissions.set(permissions)
            verb = "ساخته شد" if created else "به‌روزرسانی شد"
            self.stdout.write(
                f"{group_name}: {verb} ({len(permissions)} دسترسی)"
            )

        self.stdout.write(self.style.SUCCESS(
            "گروه‌های دسترسی کارکنان آماده است. کاربران را در پنل مدیریت "
            "(بخش کاربران و گروه‌ها) عضو این گروه‌ها کنید."
        ))
