"""
Initial migration for the orders app (Phase 2): Order, OrderItem.

Depends on discounts.0001_initial for Order.coupon -- see that
migration's docstring and discounts/migrations/0002_couponusage.py for
the full explanation of how the discounts<->orders circular reference is
sequenced without a genuine circular migration dependency.

Hand-authored -- see accounts/migrations/0002_user_phone.py's docstring
for why, and verify with `makemigrations --check --dry-run` before
relying on it in production.
"""
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("discounts", "0001_initial"),
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Order",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("order_number", models.CharField(blank=True, max_length=32, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("confirmed", "Confirmed"),
                            ("processing", "Processing"),
                            ("shipped", "Shipped"),
                            ("delivered", "Delivered"),
                            ("cancelled", "Cancelled"),
                            ("returned", "Returned"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "payment_status",
                    models.CharField(
                        choices=[
                            ("unpaid", "Unpaid"),
                            ("pending", "Pending"),
                            ("paid", "Paid"),
                            ("failed", "Failed"),
                            ("refunded", "Refunded"),
                        ],
                        default="unpaid",
                        max_length=20,
                    ),
                ),
                ("subtotal", models.PositiveBigIntegerField()),
                ("discount_amount", models.PositiveBigIntegerField(default=0)),
                ("shipping_cost", models.PositiveBigIntegerField(default=0)),
                ("total", models.PositiveBigIntegerField()),
                ("shipping_recipient_name", models.CharField(max_length=150)),
                ("shipping_phone", models.CharField(max_length=20)),
                ("shipping_province", models.CharField(max_length=100)),
                ("shipping_city", models.CharField(max_length=100)),
                ("shipping_address", models.TextField()),
                ("shipping_postal_code", models.CharField(max_length=20)),
                ("shipping_unit", models.CharField(blank=True, max_length=20)),
                ("shipping_building_number", models.CharField(blank=True, max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "coupon",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="orders",
                        to="discounts.coupon",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="orders",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Order",
                "verbose_name_plural": "Orders",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["user", "status"], name="orders_o_user_status_idx"),
                    models.Index(fields=["status", "payment_status"], name="orders_o_status_pay_idx"),
                    models.Index(fields=["created_at"], name="orders_o_created_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("product_name", models.CharField(max_length=255)),
                ("sku", models.CharField(max_length=64, verbose_name="SKU")),
                ("unit_price", models.PositiveBigIntegerField()),
                (
                    "quantity",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)]
                    ),
                ),
                ("total_price", models.PositiveBigIntegerField()),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="items", to="orders.order"
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="order_items",
                        to="products.product",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="order_items",
                        to="products.productvariant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order Item",
                "verbose_name_plural": "Order Items",
                "indexes": [
                    models.Index(fields=["order"], name="orders_oi_order_idx"),
                    models.Index(fields=["product"], name="orders_oi_product_idx"),
                ],
            },
        ),
    ]
