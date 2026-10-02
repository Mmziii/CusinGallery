"""
Initial migration for the banners app (Phase 2): Banner, DailyDeal.
Hand-authored -- see accounts/migrations/0002_user_phone.py's docstring
for why, and verify with `makemigrations --check --dry-run` before
relying on it in production.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Banner",
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
                ("ordering", models.PositiveIntegerField(default=0)),
                ("title", models.CharField(max_length=200)),
                ("subtitle", models.CharField(blank=True, max_length=300)),
                ("image", models.ImageField(upload_to="banners/")),
                ("cta_text", models.CharField(blank=True, max_length=100, verbose_name="CTA text")),
                ("cta_url", models.CharField(blank=True, max_length=300, verbose_name="CTA URL")),
                ("start_date", models.DateTimeField(blank=True, null=True)),
                ("end_date", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Banner",
                "verbose_name_plural": "Banners",
                "ordering": ["ordering"],
                "indexes": [
                    models.Index(fields=["is_active", "ordering"], name="banners_b_isactv_ord_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="DailyDeal",
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
                ("sale_price", models.PositiveBigIntegerField()),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_deals",
                        to="products.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Daily Deal",
                "verbose_name_plural": "Daily Deals",
                "ordering": ["-starts_at"],
                "indexes": [
                    models.Index(
                        fields=["is_active", "starts_at", "ends_at"], name="banners_dd_active_range_idx"
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="dailydeal",
            constraint=models.CheckConstraint(
                check=models.Q(("sale_price__gte", 0)), name="dailydeal_sale_price_gte_0"
            ),
        ),
    ]
