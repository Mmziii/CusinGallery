"""
Banners admin registration.
"""
from django.contrib import admin

from .models import Banner, DailyDeal


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "ordering", "start_date", "end_date")
    list_filter = ("is_active",)
    search_fields = ("title", "subtitle")
    ordering = ("ordering",)


@admin.register(DailyDeal)
class DailyDealAdmin(admin.ModelAdmin):
    list_display = ("product", "sale_price", "starts_at", "ends_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("product__name",)
    autocomplete_fields = ("product",)
