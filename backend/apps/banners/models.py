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

from apps.core.models import ActivableModel, OrderableModel, TimeStampedModel
from apps.products.models import Product


class Banner(TimeStampedModel, ActivableModel, OrderableModel):
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to="banners/")
    cta_text = models.CharField("CTA text", max_length=100, blank=True)
    cta_url = models.CharField("CTA URL", max_length=300, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Banner"
        verbose_name_plural = "Banners"
        ordering = ["ordering"]
        indexes = [
            models.Index(fields=["is_active", "ordering"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "Must be after the start date."})


class DailyDeal(TimeStampedModel, ActivableModel):
    """A time-boxed discounted price for a product, per master spec section 14."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="daily_deals")
    sale_price = models.PositiveBigIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        verbose_name = "Daily Deal"
        verbose_name_plural = "Daily Deals"
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
            errors["ends_at"] = "Must be after the start time."
        if self.sale_price is not None and self.product_id and self.sale_price >= self.product.price:
            errors["sale_price"] = "Deal price should be lower than the product's regular price."
        if errors:
            raise ValidationError(errors)
