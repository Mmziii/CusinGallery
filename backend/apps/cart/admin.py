"""
Cart admin registration.
"""
from django.contrib import admin
from django.db.models import Count

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("product", "variant")


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "item_count", "created_at", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)
    inlines = [CartItemInline]

    def get_queryset(self, request):
        # select_related("user"): the `user` list_display column would
        # otherwise issue one lazy query per row (Django Admin doesn't
        # select_related list_display FK columns automatically).
        # annotate(_item_count=...): computed once for the whole
        # changelist, not per row -- see item_count() below.
        return super().get_queryset(request).select_related("user").annotate(_item_count=Count("items"))

    @admin.display(description="Items", ordering="_item_count")
    def item_count(self, obj):
        # A plain row count, not the storefront's own item_count (sum of
        # quantities) from apps.cart.services.build_cart_view --
        # deliberately a cheap DB aggregate for this staff-only list
        # column rather than pulling in that pricing-aware computation.
        return obj._item_count
