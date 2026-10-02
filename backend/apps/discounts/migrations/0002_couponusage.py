"""
Creates CouponUsage (Phase 2). Deliberately a separate, later migration --
see 0001_initial.py's docstring for why this couldn't be created alongside
Coupon: it has a FK to orders.Order, which itself has a FK to this app's
Coupon, so this migration depends on orders.0001_initial having already
run.

Hand-authored -- see accounts/migrations/0002_user_phone.py's docstring
for why, and verify with `makemigrations --check --dry-run` before
relying on it in production.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("discounts", "0001_initial"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CouponUsage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("used_at", models.DateTimeField(auto_now_add=True)),
                (
                    "coupon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="usages",
                        to="discounts.coupon",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="coupon_usages",
                        to="orders.order",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coupon_usages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Coupon Usage",
                "verbose_name_plural": "Coupon Usages",
                "ordering": ["-used_at"],
                "indexes": [
                    models.Index(fields=["coupon", "user"], name="discounts_cu_coupon_user_idx"),
                ],
            },
        ),
    ]
