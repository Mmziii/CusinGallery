"""
Products models.

Introduced in Phase 2 (Database Architecture & Models), per master spec
sections 9-12. Variants use a lightweight attribute/value system (Color,
Size, ...) rather than a rigid fixed set of variant dimensions, so new
attribute types can be added later purely through data entry in Django
admin, never a schema change.

Pricing convention: all monetary fields are stored as whole Toman
integers (PositiveBigIntegerField), not DecimalField. Iranian Toman has
no practical fractional subunit, and this matches the frontend's
formatPrice() utility (Phase 1, src/utils/formatPrice.js), which already
assumes and formats plain integer amounts.
"""
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.categories.models import Category
from apps.core.models import ActivableModel, OrderableModel, TimeStampedModel


class Brand(TimeStampedModel, ActivableModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    logo = models.ImageField(upload_to="brands/", blank=True, null=True)

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TimeStampedModel, ActivableModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True)
    sku = models.CharField("SKU", max_length=64, unique=True)

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, related_name="products", null=True, blank=True
    )

    short_description = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)

    price = models.PositiveBigIntegerField()
    compare_at_price = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Optional 'was' price shown struck through. Must be >= price.",
    )
    discount_percentage = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)

    is_featured = models.BooleanField(default=False)
    is_new = models.BooleanField(default=False)
    is_best_seller = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "is_featured"]),
            models.Index(fields=["is_active", "is_new"]),
            models.Index(fields=["is_active", "is_best_seller"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["brand", "is_active"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.compare_at_price is not None and self.price is not None:
            if self.compare_at_price < self.price:
                raise ValidationError(
                    {"compare_at_price": "Compare-at price cannot be lower than the selling price."}
                )

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0


class ProductImage(TimeStampedModel, OrderableModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Product Image"
        verbose_name_plural = "Product Images"
        ordering = ["ordering"]
        constraints = [
            # At most one primary image per product, enforced at the
            # database level via a partial unique index.
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="unique_primary_image_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} image #{self.pk or '?'}"


class ProductAttribute(models.Model):
    """e.g. 'Color', 'Size', 'Capacity' -- see master spec section 12."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        verbose_name = "Product Attribute"
        verbose_name_plural = "Product Attributes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductAttributeValue(models.Model):
    """e.g. Color='Red', Size='Large'."""

    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Product Attribute Value"
        verbose_name_plural = "Product Attribute Values"
        ordering = ["attribute", "value"]
        constraints = [
            models.UniqueConstraint(fields=["attribute", "value"], name="unique_value_per_attribute"),
        ]

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"


class ProductVariant(TimeStampedModel, ActivableModel):
    """
    A purchasable variation of a product (e.g. 'Red / Large'), per master
    spec section 12. Not every product needs variants -- a product with
    no ProductVariant rows is sold directly against Product.price /
    Product.stock_quantity.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField("SKU", max_length=64, unique=True)
    attribute_values = models.ManyToManyField(
        ProductAttributeValue, related_name="variants", blank=True
    )

    price = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Leave empty to use the parent product's price."
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    image = models.ForeignKey(
        ProductImage, on_delete=models.SET_NULL, null=True, blank=True, related_name="variants"
    )

    class Meta:
        verbose_name = "Product Variant"
        verbose_name_plural = "Product Variants"
        indexes = [
            models.Index(fields=["product", "is_active"]),
        ]

    def __str__(self):
        return f"{self.product.name} ({self.sku})"

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.product.price
