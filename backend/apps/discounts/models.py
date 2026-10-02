"""
Discounts models.

Introduced in Phase 2 (Database Architecture & Models), per master spec
section 29. Coupon validation LOGIC (applying a code at checkout,
enforcing limits transactionally) is explicitly Phase 6 business work --
"never trust discount calculations from frontend" -- this phase only
establishes the schema those checks will run against, plus the couple of
field-level/cross-field validations (clean()) that belong on the model
regardless of which view calls it.

Cross-app relationship note: Coupon is referenced by Order (Phase 2,
apps.orders) via FK, and CouponUsage below references Order back. That's
a genuine two-way relationship between the "discounts" and "orders" apps.
To avoid a circular Python import (apps.orders.models importing this
module AND this module importing apps.orders.models), CouponUsage.order
below uses Django's lazy "app_label.ModelName" string reference instead
of importing the Order class directly. The circular *migration*
dependency this could otherwise create is avoided by splitting this app's
migrations in two -- see migrations/0002_couponusage.py for exactly how.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.categories.models import Category
from apps.core.models import ActivableModel, TimeStampedModel
from apps.products.models import Product


class Coupon(TimeStampedModel, ActivableModel):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed amount"

    code = models.CharField(max_length=32, unique=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)

    percentage_value = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Required and 1-100 when discount_type is 'percentage'."
    )
    fixed_value = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Required (Toman) when discount_type is 'fixed'."
    )
    maximum_discount_amount = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Caps a percentage discount's Toman value. Ignored for fixed coupons."
    )
    minimum_order_amount = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Order subtotal must reach this (Toman) for the coupon to apply."
    )

    start_date = models.DateTimeField(null=True, blank=True)
    expiration_date = models.DateTimeField(null=True, blank=True)

    usage_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Total redemptions allowed across all users. Empty = unlimited."
    )
    per_user_usage_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Redemptions allowed per user. Empty = unlimited."
    )

    applicable_products = models.ManyToManyField(
        Product, related_name="coupons", blank=True, help_text="Empty = applies store-wide."
    )
    applicable_categories = models.ManyToManyField(
        Category, related_name="coupons", blank=True, help_text="Empty = applies store-wide."
    )

    class Meta:
        verbose_name = "Coupon"
        verbose_name_plural = "Coupons"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "expiration_date"]),
        ]

    def __str__(self):
        return self.code

    def clean(self):
        errors = {}
        if self.discount_type == self.DiscountType.PERCENTAGE:
            if self.percentage_value is None:
                errors["percentage_value"] = "Required for a percentage coupon."
            elif not (1 <= self.percentage_value <= 100):
                errors["percentage_value"] = "Must be between 1 and 100."
        elif self.discount_type == self.DiscountType.FIXED:
            if not self.fixed_value:
                errors["fixed_value"] = "Required (and > 0) for a fixed-amount coupon."

        if self.start_date and self.expiration_date and self.expiration_date <= self.start_date:
            errors["expiration_date"] = "Must be after the start date."

        if errors:
            raise ValidationError(errors)


class CouponUsage(models.Model):
    """
    One row per successful coupon redemption -- what per_user_usage_limit
    and usage_limit are actually enforced against (Phase 6). `order` is
    SET_NULL rather than CASCADE so the usage record (and therefore the
    user's redemption count) survives even in the unusual case an order
    record is later removed.
    """

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="usages")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_usages"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        related_name="coupon_usages",
        null=True,
        blank=True,
    )
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Coupon Usage"
        verbose_name_plural = "Coupon Usages"
        ordering = ["-used_at"]
        indexes = [
            models.Index(fields=["coupon", "user"]),
        ]

    def __str__(self):
        return f"{self.user} used {self.coupon.code}"
