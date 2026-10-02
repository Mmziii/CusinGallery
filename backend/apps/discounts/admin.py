"""
Discounts admin registration.
"""
from django.contrib import admin

from .models import Coupon, CouponUsage


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code", "discount_type", "percentage_value", "fixed_value",
        "is_active", "usage_limit", "expiration_date",
    )
    list_filter = ("is_active", "discount_type")
    search_fields = ("code",)
    autocomplete_fields = ("applicable_products", "applicable_categories")
    fieldsets = (
        (None, {"fields": ("code", "discount_type", "is_active")}),
        ("Value", {"fields": ("percentage_value", "fixed_value", "maximum_discount_amount")}),
        ("Conditions", {"fields": ("minimum_order_amount", "applicable_products", "applicable_categories")}),
        ("Validity", {"fields": ("start_date", "expiration_date")}),
        ("Usage limits", {"fields": ("usage_limit", "per_user_usage_limit")}),
    )


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "used_at")
    search_fields = ("coupon__code", "user__username", "user__email")
    autocomplete_fields = ("coupon", "user", "order")
    list_filter = ("used_at",)
