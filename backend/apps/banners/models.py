"""
Banners models.

Introduced in Phase 2 (Database Architecture & Models), per master spec
sections 13-14 & 33. Covers homepage content management: promotional
banners and time-boxed daily deals. Rendering these on the homepage (and
generating the deal countdown from `ends_at`, per the master spec's "do
NOT create a fake endless countdown") is Phase 8/9 frontend + view work;
this phase only establishes the schema those views will read from.
"""
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.image_files import validate_image_file
from apps.core.models import ActivableModel, OrderableModel, TimeStampedModel
from apps.products.models import Product


class Banner(TimeStampedModel, ActivableModel, OrderableModel):
    title = models.CharField("عنوان", max_length=200)
    subtitle = models.CharField("زیرعنوان", max_length=300, blank=True)
    image = models.ImageField("تصویر", upload_to="banners/", validators=[validate_image_file])
    # Responsive WebP re-encodes (Part 3) -- progressive enhancement;
    # empty means "serve the original".
    webp_400 = models.CharField(max_length=255, blank=True, default="")
    webp_800 = models.CharField(max_length=255, blank=True, default="")
    webp_1200 = models.CharField(max_length=255, blank=True, default="")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image and not self.webp_400:
            from apps.core.image_files import make_responsive_variants

            variants = make_responsive_variants(self.image)
            if variants:
                self.webp_400 = variants.get(400, "")
                self.webp_800 = variants.get(800, "")
                self.webp_1200 = variants.get(1200, "")
                super().save(update_fields=["webp_400", "webp_800", "webp_1200", "updated_at"])
    cta_text = models.CharField("متن دکمهٔ اقدام", max_length=100, blank=True)
    cta_url = models.CharField("لینک دکمهٔ اقدام", max_length=300, blank=True)
    start_date = models.DateTimeField("تاریخ شروع نمایش", null=True, blank=True)
    end_date = models.DateTimeField("تاریخ پایان نمایش", null=True, blank=True)

    class Meta:
        verbose_name = "بنر"
        verbose_name_plural = "بنرها"
        ordering = ["ordering"]
        indexes = [
            models.Index(fields=["is_active", "ordering"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "باید بعد از تاریخ شروع باشد."})


class DailyDeal(TimeStampedModel, ActivableModel):
    """A time-boxed discounted price for a product, per master spec section 14."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="daily_deals", verbose_name="محصول"
    )
    sale_price = models.PositiveBigIntegerField("قیمت پیشنهاد روزانه (تومان)")
    starts_at = models.DateTimeField("زمان شروع")
    ends_at = models.DateTimeField("زمان پایان")

    class Meta:
        verbose_name = "پیشنهاد روزانه"
        verbose_name_plural = "پیشنهادهای روزانه"
        ordering = ["-starts_at"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(sale_price__gte=0), name="dailydeal_sale_price_gte_0"),
        ]

    def __str__(self):
        return f"{self.product.name} deal"

    def clean(self):
        errors = {}
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "باید بعد از زمان شروع باشد."
        if self.sale_price is not None and self.product_id and self.sale_price >= self.product.price:
            errors["sale_price"] = "قیمت پیشنهاد باید از قیمت عادی محصول کمتر باشد."
        if errors:
            raise ValidationError(errors)
