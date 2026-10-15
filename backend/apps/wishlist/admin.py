"""
Wishlist admin registration.
"""
from django.contrib import admin

from apps.adminui.admin_dates import jalali_column

from .models import WishlistItem


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", jalali_column("created_at", "تاریخ افزودن", with_time=True))
    # Django Admin does NOT automatically select_related for FK columns
    # shown in list_display -- without this, each row's `user`/`product`
    # column would issue its own lazy query (a real N+1 in the admin
    # changelist itself, not just customer-facing endpoints).
    list_select_related = ("user", "product")
    search_fields = ("user__username", "user__email", "product__name")
    autocomplete_fields = ("user", "product")
    list_filter = ("created_at",)
