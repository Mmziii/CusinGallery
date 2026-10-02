"""
Initial migration for categories.Category (Phase 2). Hand-authored --
see accounts/migrations/0002_user_phone.py's docstring for why, and
verify with `makemigrations --check --dry-run` before relying on it.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Category",
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
                ("name", models.CharField(max_length=150)),
                ("slug", models.SlugField(max_length=170, unique=True)),
                ("image", models.ImageField(blank=True, null=True, upload_to="categories/")),
                ("description", models.TextField(blank=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        help_text="Leave empty for a top-level category.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="children",
                        to="categories.category",
                    ),
                ),
            ],
            options={
                "verbose_name": "Category",
                "verbose_name_plural": "Categories",
                "ordering": ["ordering", "name"],
            },
        ),
        migrations.AddIndex(
            model_name="category",
            index=models.Index(fields=["parent", "is_active"], name="categories__parent__idx"),
        ),
        migrations.AddIndex(
            model_name="category",
            index=models.Index(fields=["is_active", "ordering"], name="categories__isactv_ord_idx"),
        ),
    ]
