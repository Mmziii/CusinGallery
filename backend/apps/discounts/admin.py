"""
Discounts admin registration (Phase B - Store management).

The coupon *engine* (applying codes at checkout, enforcing limits under
row locks) lives in apps/discounts/services.py; the admin here is the
owner's day-to-day view of what coupons exist, how much they've been
used, and whether they're live.
"""
from django.contrib import admin, messages
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from .models import Coupon, CouponUsage


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code", "discount_summary", "status_badge", "usage_summary",
        "minimum_order_amount", "start_date", "expiration_date",
    )
    list_filter = ("is_active", "discount_type", "start_date", "expiration_date")
    search_fields = ("code",)
    autocomplete_fields = ("applicable_products", "applicable_categories")
    actions = ["activate_coupons", "deactivate_coupons"]
    fieldsets = (
        (None, {"fields": ("code", "discount_type", "is_active")}),
        ("Value", {"fields": ("percentage_value", "fixed_value", "maximum_discount_amount")}),
        ("Conditions", {"fields": ("minimum_order_amount", "applicable_products", "applicable_categories")}),
        ("Validity", {"fields": ("start_date", "expiration_date")}),
        ("Usage limits", {"fields": ("usage_limit", "per_user_usage_limit")}),
    )

    def get_queryset(self, request):
        # One annotated count per coupon -- the usage column must not run
        # a query per row.
        return super().get_queryset(request).annotate(usage_count=Count("usages"))

    def discount_summary(self, obj):
        if obj.discount_type == Coupon.DiscountType.PERCENTAGE:
            text = f"{obj.percentage_value}%"
            if obj.maximum_discount_amount:
                text += f" (max {obj.maximum_discount_amount:,})"
            return text
        return f"{obj.fixed_value:,} Toman"

    discount_summary.short_description = "تخفیف"

    def usage_summary(self, obj):
        used = getattr(obj, "usage_count", 0)
        if obj.usage_limit is None:
            return f"{used} بار استفاده شده"
        return f"{used} از {obj.usage_limit} بار استفاده شده"

    usage_summary.short_description = "میزان استفاده"
    usage_summary.admin_order_field = "usage_count"

    def status_badge(self, obj):
        now = timezone.now()
        if not obj.is_active:
            label, color = "غیرفعال", "#888"
        elif obj.expiration_date and obj.expiration_date <= now:
            label, color = "منقضی شده", "#b30000"
        elif obj.start_date and obj.start_date > now:
            label, color = "زمان‌بندی‌شده", "#a05a00"
        else:
            label, color = "فعال", "#1a7f37"
        return format_html('<span style="color:{};font-weight:bold">{}</span>', color, label)

    status_badge.short_description = "وضعیت"

    @admin.action(description="فعال‌سازی کوپن‌های انتخاب‌شده")
    def activate_coupons(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} کوپن فعال شد.", messages.SUCCESS)

    @admin.action(description="غیرفعال‌سازی کوپن‌های انتخاب‌شده")
    def deactivate_coupons(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} کوپن غیرفعال شد.", messages.SUCCESS)


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "used_at")
    search_fields = ("coupon__code", "user__username", "user__email")
    autocomplete_fields = ("coupon", "user", "order")
    list_filter = ("used_at",)

    def has_add_permission(self, request):
        # Usage rows are written by the checkout/payment flow only.
        return False
