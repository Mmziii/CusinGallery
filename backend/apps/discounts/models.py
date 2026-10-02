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
        PERCENTAGE = "percentage", "درصدی"
        FIXED = "fixed", "مبلغ ثابت"

    code = models.CharField(
        "کد کوپن", max_length=32, unique=True, help_text="کدی که مشتری هنگام خرید وارد می‌کند."
    )
    discount_type = models.CharField("نوع تخفیف", max_length=10, choices=DiscountType.choices)

    percentage_value = models.PositiveSmallIntegerField(
        "درصد تخفیف", null=True, blank=True,
        help_text="برای کوپن درصدی لازم است؛ عددی بین ۱ تا ۱۰۰.",
    )
    fixed_value = models.PositiveBigIntegerField(
        "مبلغ تخفیف (تومان)", null=True, blank=True,
        help_text="برای کوپن مبلغ ثابت لازم است.",
    )
    maximum_discount_amount = models.PositiveBigIntegerField(
        "سقف تخفیف (تومان)", null=True, blank=True,
        help_text="بیشینهٔ تخفیف کوپن‌های درصدی. برای کوپن مبلغ ثابت نادیده گرفته می‌شود.",
    )
    minimum_order_amount = models.PositiveBigIntegerField(
        "حداقل مبلغ سفارش (تومان)", null=True, blank=True,
        help_text="جمع اقلام باید حداقل به این مبلغ برسد تا کوپن اعمال شود.",
    )

    start_date = models.DateTimeField("تاریخ شروع", null=True, blank=True)
    expiration_date = models.DateTimeField("تاریخ انقضا", null=True, blank=True)

    usage_limit = models.PositiveIntegerField(
        "سقف استفادهٔ کل", null=True, blank=True,
        help_text="حداکثر تعداد استفاده برای همهٔ کاربران. خالی = نامحدود.",
    )
    per_user_usage_limit = models.PositiveIntegerField(
        "سقف استفادهٔ هر کاربر", null=True, blank=True,
        help_text="حداکثر تعداد استفاده برای هر کاربر. خالی = نامحدود.",
    )

    applicable_products = models.ManyToManyField(
        Product, related_name="coupons", blank=True, verbose_name="محصولات مشمول",
        help_text="خالی = روی همهٔ فروشگاه اعمال می‌شود.",
    )
    applicable_categories = models.ManyToManyField(
        Category, related_name="coupons", blank=True, verbose_name="دسته‌بندی‌های مشمول",
        help_text="خالی = روی همهٔ فروشگاه اعمال می‌شود.",
    )

    class Meta:
        verbose_name = "کوپن تخفیف"
        verbose_name_plural = "کوپن‌های تخفیف"
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
                errors["percentage_value"] = "برای کوپن درصدی لازم است."
            elif not (1 <= self.percentage_value <= 100):
                errors["percentage_value"] = "باید عددی بین ۱ تا ۱۰۰ باشد."
        elif self.discount_type == self.DiscountType.FIXED:
            if not self.fixed_value:
                errors["fixed_value"] = "برای کوپن مبلغ ثابت لازم است (و باید بزرگ‌تر از صفر باشد)."

        if self.start_date and self.expiration_date and self.expiration_date <= self.start_date:
            errors["expiration_date"] = "باید بعد از تاریخ شروع باشد."

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

    coupon = models.ForeignKey(
        Coupon, on_delete=models.CASCADE, related_name="usages", verbose_name="کوپن"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_usages",
        verbose_name="کاربر",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        related_name="coupon_usages",
        null=True,
        blank=True,
        verbose_name="سفارش",
    )
    used_at = models.DateTimeField("زمان استفاده", auto_now_add=True)

    class Meta:
        verbose_name = "استفاده از کوپن"
        verbose_name_plural = "استفاده‌های کوپن"
        ordering = ["-used_at"]
        indexes = [
            models.Index(fields=["coupon", "user"]),
        ]

    def __str__(self):
        return f"{self.user} used {self.coupon.code}"
