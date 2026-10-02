"""
Banners admin registration (Phase B - Store management).

Banners and daily deals are time-boxed; the list views show whether
each one is live RIGHT NOW (the same window logic the public API uses,
apps/banners/views.py) so the owner sees exactly what customers see.
"""
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from .models import Banner, DailyDeal


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = (
        "preview", "title", "status_badge", "is_active", "ordering",
        "start_date", "end_date",
    )
    list_filter = ("is_active", "start_date", "end_date")
    list_editable = ("ordering",)
    search_fields = ("title", "subtitle")
    ordering = ("ordering",)
    actions = ["activate_banners", "deactivate_banners"]

    def preview(self, obj):
        if not obj.image:
            return "—"
        return format_html('<img src="{}" alt="" style="max-height:44px;max-width:160px">', obj.image.url)

    preview.short_description = ""

    def status_badge(self, obj):
        now = timezone.now()
        # Same window logic as the public endpoint (apps/banners/views.py):
        # start_date null-or-passed AND end_date null-or-not-yet-passed.
        started = obj.start_date is None or obj.start_date <= now
        ended = obj.end_date is not None and obj.end_date < now
        if obj.is_active and started and not ended:
            return format_html('<span style="color:#1a7f37;font-weight:bold">در حال نمایش</span>')
        if obj.end_date and ended:
            return format_html('<span style="color:#b30000">پایان‌یافته</span>')
        if not started:
            return format_html('<span style="color:#a05a00">زمان‌بندی‌شده</span>')
        return format_html('<span style="color:#888">غیرفعال</span>')

    status_badge.short_description = "وضعیت نمایش"

    @admin.action(description="فعال‌سازی بنرهای انتخاب‌شده")
    def activate_banners(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} بنر فعال شد.", messages.SUCCESS)

    @admin.action(description="غیرفعال‌سازی بنرهای انتخاب‌شده")
    def deactivate_banners(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} بنر غیرفعال شد.", messages.SUCCESS)


@admin.register(DailyDeal)
class DailyDealAdmin(admin.ModelAdmin):
    list_display = (
        "product", "sale_price", "regular_price", "status_badge",
        "is_active", "starts_at", "ends_at",
    )
    list_filter = ("is_active", "starts_at", "ends_at")
    search_fields = ("product__name",)
    autocomplete_fields = ("product",)
    actions = ["activate_deals", "deactivate_deals"]

    def regular_price(self, obj):
        return obj.product.price if obj.product_id else "—"

    regular_price.short_description = "قیمت عادی"
    regular_price.admin_order_field = "product__price"

    def status_badge(self, obj):
        now = timezone.now()
        if obj.is_active and obj.starts_at <= now <= obj.ends_at:
            return format_html('<span style="color:#1a7f37;font-weight:bold">در حال اجرا</span>')
        if obj.ends_at <= now:
            return format_html('<span style="color:#b30000">پایان‌یافته</span>')
        if obj.starts_at > now:
            return format_html('<span style="color:#a05a00">زمان‌بندی‌شده</span>')
        return format_html('<span style="color:#888">غیرفعال</span>')

    status_badge.short_description = "وضعیت نمایش"

    @admin.action(description="فعال‌سازی پیشنهادهای انتخاب‌شده")
    def activate_deals(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} پیشنهاد فعال شد.", messages.SUCCESS)

    @admin.action(description="غیرفعال‌سازی پیشنهادهای انتخاب‌شده")
    def deactivate_deals(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} پیشنهاد غیرفعال شد.", messages.SUCCESS)
