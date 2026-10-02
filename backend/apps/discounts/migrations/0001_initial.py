"""
Initial migration for the discounts app (Phase 2): Coupon only.

CouponUsage is deliberately NOT in this migration -- it has a FK to
orders.Order, and Order has a FK back to this app's Coupon. Creating both
directions in each app's very first migration would be a genuine circular
migration dependency (discounts.0001 needing orders.0001, and orders.0001
needing discounts.0001, at the same time). Splitting this app's migrations
in two breaks the cycle into a clean line:

    discounts.0001 (Coupon)
        -> orders.0001 (Order, FK to discounts.Coupon)
            -> discounts.0002 (CouponUsage, FK to orders.Order)

See migrations/0002_couponusage.py for that second migration, and
apps/discounts/models.py / apps/orders/models.py for the corresponding
lazy string FK references that avoid the equivalent circular *Python
import* problem.

Hand-authored -- see accounts/migrations/0002_user_phone.py's docstring
for why, and verify with `makemigrations --check --dry-run` before
relying on it in production.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("categories", "0001_initial"),
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Coupon",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("code", models.CharField(max_length=32, unique=True)),
                (
                    "discount_type",
                    models.CharField(
                        choices=[("percentage", "Percentage"), ("fixed", "Fixed amount")], max_length=10
                    ),
                ),
                (
                    "percentage_value",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text="Required and 1-100 when discount_type is 'percentage'.",
                        null=True,
                    ),
                ),
                (
                    "fixed_value",
                    models.PositiveBigIntegerField(
                        blank=True, help_text="Required (Toman) when discount_type is 'fixed'.", null=True
                    ),
                ),
                (
                    "maximum_discount_amount",
                    models.PositiveBigIntegerField(
                        blank=True,
                        help_text="Caps a percentage discount's Toman value. Ignored for fixed coupons.",
                        null=True,
                    ),
                ),
                (
                    "minimum_order_amount",
                    models.PositiveBigIntegerField(
                        blank=True,
                        help_text="Order subtotal must reach this (Toman) for the coupon to apply.",
                        null=True,
                    ),
                ),
                ("start_date", models.DateTimeField(blank=True, null=True)),
                ("expiration_date", models.DateTimeField(blank=True, null=True)),
                (
                    "usage_limit",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Total redemptions allowed across all users. Empty = unlimited.",
                        null=True,
                    ),
                ),
                (
                    "per_user_usage_limit",
                    models.PositiveIntegerField(
                        blank=True, help_text="Redemptions allowed per user. Empty = unlimited.", null=True
                    ),
                ),
                (
                    "applicable_categories",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Empty = applies store-wide.",
                        related_name="coupons",
                        to="categories.category",
                    ),
                ),
                (
                    "applicable_products",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Empty = applies store-wide.",
                        related_name="coupons",
                        to="products.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Coupon",
                "verbose_name_plural": "Coupons",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["is_active", "expiration_date"], name="discounts_c_isactv_exp_idx"
                    ),
                ],
            },
        ),
    ]
