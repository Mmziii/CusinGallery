"""
Initial migration for the products app (Phase 2): Brand, Product,
ProductImage, ProductAttribute, ProductAttributeValue, ProductVariant.
Hand-authored -- see accounts/migrations/0002_user_phone.py's docstring
for why, and verify with `makemigrations --check --dry-run` before
relying on it in production.
"""
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("categories", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Brand",
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
                ("name", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                ("logo", models.ImageField(blank=True, null=True, upload_to="brands/")),
            ],
            options={
                "verbose_name": "Brand",
                "verbose_name_plural": "Brands",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Product",
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
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=280, unique=True)),
                ("sku", models.CharField(max_length=64, unique=True, verbose_name="SKU")),
                ("short_description", models.CharField(blank=True, max_length=500)),
                ("description", models.TextField(blank=True)),
                ("price", models.PositiveBigIntegerField()),
                (
                    "compare_at_price",
                    models.PositiveBigIntegerField(
                        blank=True,
                        help_text="Optional 'was' price shown struck through. Must be >= price.",
                        null=True,
                    ),
                ),
                (
                    "discount_percentage",
                    models.PositiveSmallIntegerField(
                        default=0,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                ("stock_quantity", models.PositiveIntegerField(default=0)),
                ("low_stock_threshold", models.PositiveIntegerField(default=5)),
                ("is_featured", models.BooleanField(default=False)),
                ("is_new", models.BooleanField(default=False)),
                ("is_best_seller", models.BooleanField(default=False)),
                (
                    "brand",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="products",
                        to="products.brand",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="products",
                        to="categories.category",
                    ),
                ),
            ],
            options={
                "verbose_name": "Product",
                "verbose_name_plural": "Products",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["is_active", "is_featured"], name="products_p_isactv_feat_idx"),
                    models.Index(fields=["is_active", "is_new"], name="products_p_isactv_new_idx"),
                    models.Index(fields=["is_active", "is_best_seller"], name="products_p_isactv_best_idx"),
                    models.Index(fields=["category", "is_active"], name="products_p_categ_isactv_idx"),
                    models.Index(fields=["brand", "is_active"], name="products_p_brand_isactv_idx"),
                    models.Index(fields=["price"], name="products_p_price_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ProductImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("ordering", models.PositiveIntegerField(default=0)),
                ("image", models.ImageField(upload_to="products/")),
                ("alt_text", models.CharField(blank=True, max_length=255)),
                ("is_primary", models.BooleanField(default=False)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="products.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Product Image",
                "verbose_name_plural": "Product Images",
                "ordering": ["ordering"],
            },
        ),
        migrations.CreateModel(
            name="ProductAttribute",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
                ("slug", models.SlugField(max_length=120, unique=True)),
            ],
            options={
                "verbose_name": "Product Attribute",
                "verbose_name_plural": "Product Attributes",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ProductAttributeValue",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("value", models.CharField(max_length=100)),
                (
                    "attribute",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="values",
                        to="products.productattribute",
                    ),
                ),
            ],
            options={
                "verbose_name": "Product Attribute Value",
                "verbose_name_plural": "Product Attribute Values",
                "ordering": ["attribute", "value"],
            },
        ),
        migrations.CreateModel(
            name="ProductVariant",
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
                ("sku", models.CharField(max_length=64, unique=True, verbose_name="SKU")),
                (
                    "price",
                    models.PositiveBigIntegerField(
                        blank=True, help_text="Leave empty to use the parent product's price.", null=True
                    ),
                ),
                ("stock_quantity", models.PositiveIntegerField(default=0)),
                (
                    "attribute_values",
                    models.ManyToManyField(
                        blank=True, related_name="variants", to="products.productattributevalue"
                    ),
                ),
                (
                    "image",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="variants",
                        to="products.productimage",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="variants",
                        to="products.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Product Variant",
                "verbose_name_plural": "Product Variants",
                "indexes": [
                    models.Index(fields=["product", "is_active"], name="products_pv_prod_isactv_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="productimage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_primary", True)),
                fields=("product",),
                name="unique_primary_image_per_product",
            ),
        ),
        migrations.AddConstraint(
            model_name="productattributevalue",
            constraint=models.UniqueConstraint(
                fields=("attribute", "value"), name="unique_value_per_attribute"
            ),
        ),
    ]
