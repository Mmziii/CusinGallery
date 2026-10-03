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
from apps.core.image_files import validate_image_file
from apps.core.models import ActivableModel, OrderableModel, TimeStampedModel


class Brand(TimeStampedModel, ActivableModel):
    name = models.CharField("نام", max_length=120, unique=True)
    slug = models.SlugField("شناسه (آدرس)", max_length=140, unique=True, allow_unicode=True)
    logo = models.ImageField("لوگو", upload_to="brands/", blank=True, null=True, validators=[validate_image_file])

    class Meta:
        verbose_name = "برند"
        verbose_name_plural = "برندها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TimeStampedModel, ActivableModel):
    name = models.CharField("نام محصول", max_length=255)
    slug = models.SlugField("شناسه (آدرس)", max_length=280, unique=True, allow_unicode=True)
    sku = models.CharField("کد کالا (SKU)", max_length=64, unique=True)

    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", verbose_name="دسته‌بندی"
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, related_name="products", null=True, blank=True,
        verbose_name="برند",
    )

    short_description = models.CharField("توضیح کوتاه", max_length=500, blank=True)
    description = models.TextField("توضیحات کامل", blank=True)

    price = models.PositiveBigIntegerField("قیمت (تومان)")
    compare_at_price = models.PositiveBigIntegerField(
        "قیمت قبل از تخفیف (تومان)",
        null=True,
        blank=True,
        help_text="قیمت خط‌خوردهٔ نمایشی. در صورت درج باید بزرگ‌تر یا مساوی قیمت فروش باشد.",
    )
    discount_percentage = models.PositiveSmallIntegerField(
        "درصد تخفیف", default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    stock_quantity = models.PositiveIntegerField("موجودی", default=0)
    low_stock_threshold = models.PositiveIntegerField(
        "آستانهٔ هشدار موجودی کم", default=5,
        help_text="وقتی موجودی به این عدد برسد، در فهرست محصولات هشدار کمبود موجودی نمایش داده می‌شود.",
    )

    is_featured = models.BooleanField(
        "محصول ویژه", default=False, help_text="در بخش «محصولات ویژه» صفحهٔ اصلی نمایش داده می‌شود."
    )
    is_new = models.BooleanField("محصول جدید", default=False)
    is_best_seller = models.BooleanField("محصول پرفروش", default=False)

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
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
                    {"compare_at_price": "قیمت قبل از تخفیف نمی‌تواند کمتر از قیمت فروش باشد."}
                )

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0


class ProductImage(TimeStampedModel, OrderableModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images", verbose_name="محصول"
    )
    image = models.ImageField("تصویر", upload_to="products/", validators=[validate_image_file])
    alt_text = models.CharField("متن جایگزین", max_length=255, blank=True)
    is_primary = models.BooleanField(
        "تصویر اصلی", default=False, help_text="برای هر محصول فقط یک تصویر اصلی وجود دارد."
    )
    # Downscaled JPEG generated once at upload time (save() below) and
    # used by admin list views; never re-encoded at render time.
    thumbnail = models.ImageField("پیش‌نمایش", upload_to="products/thumbnails/", blank=True)

    class Meta:
        verbose_name = "تصویر محصول"
        verbose_name_plural = "تصاویر محصول"
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Generate the thumbnail exactly once per stored image: only
        # when an image exists and no thumbnail has been stored yet.
        if self.image and not self.thumbnail:
            from apps.core.image_files import make_thumbnail

            saved = make_thumbnail(self.image)
            if saved:
                self.thumbnail = saved
                super().save(update_fields=["thumbnail", "updated_at"])

    def __str__(self):
        return f"{self.product.name} image #{self.pk or '?'}"


class ProductAttribute(models.Model):
    """e.g. 'Color', 'Size', 'Capacity' -- see master spec section 12."""

    name = models.CharField("نام ویژگی", max_length=100, unique=True)
    slug = models.SlugField("شناسه (آدرس)", max_length=120, unique=True, allow_unicode=True)

    class Meta:
        verbose_name = "ویژگی محصول"
        verbose_name_plural = "ویژگی‌های محصول"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductAttributeValue(models.Model):
    """e.g. Color='Red', Size='Large'."""

    attribute = models.ForeignKey(
        ProductAttribute, on_delete=models.CASCADE, related_name="values", verbose_name="ویژگی"
    )
    value = models.CharField("مقدار", max_length=100)

    class Meta:
        verbose_name = "مقدار ویژگی"
        verbose_name_plural = "مقادیر ویژگی"
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

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants", verbose_name="محصول"
    )
    sku = models.CharField("کد کالا (SKU)", max_length=64, unique=True)
    attribute_values = models.ManyToManyField(
        ProductAttributeValue, related_name="variants", blank=True, verbose_name="مقادیر ویژگی"
    )

    price = models.PositiveBigIntegerField(
        "قیمت (تومان)", null=True, blank=True,
        help_text="خالی بگذارید تا قیمت خود محصول استفاده شود.",
    )
    stock_quantity = models.PositiveIntegerField("موجودی", default=0)
    image = models.ForeignKey(
        ProductImage, on_delete=models.SET_NULL, null=True, blank=True, related_name="variants",
        verbose_name="تصویر",
    )

    class Meta:
        verbose_name = "تنوع محصول"
        verbose_name_plural = "تنوع‌های محصول"
        indexes = [
            models.Index(fields=["product", "is_active"]),
        ]

    def __str__(self):
        return f"{self.product.name} ({self.sku})"

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.product.price
