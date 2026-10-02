"""
Creates Address (Phase 2). See apps/accounts/models.py for the field
definitions this must match. Hand-authored -- see 0002_user_phone.py's
docstring for why, and verify with `makemigrations --check --dry-run`
before relying on it in production.
"""
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0002_user_phone"),
    ]

    operations = [
        migrations.CreateModel(
            name="Address",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("recipient_name", models.CharField(max_length=150)),
                (
                    "phone",
                    models.CharField(
                        max_length=20,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Enter a valid phone number (digits only, optionally prefixed with +).",
                                regex="^\\+?\\d{7,15}$",
                            )
                        ],
                    ),
                ),
                ("province", models.CharField(max_length=100)),
                ("city", models.CharField(max_length=100)),
                ("address", models.TextField()),
                ("postal_code", models.CharField(max_length=20)),
                ("unit", models.CharField(blank=True, max_length=20)),
                ("building_number", models.CharField(blank=True, max_length=20)),
                ("is_default", models.BooleanField(default=False)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="addresses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Address",
                "verbose_name_plural": "Addresses",
                "ordering": ["-is_default", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="address",
            index=models.Index(fields=["user"], name="addr_user_idx"),
        ),
        migrations.AddConstraint(
            model_name="address",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("user",),
                name="addr_one_default_per_user",
            ),
        ),
    ]
