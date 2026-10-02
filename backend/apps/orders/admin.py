"""
Orders admin registration.
"""
from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product", "variant", "product_name", "sku", "unit_price", "quantity", "total_price")
    readonly_fields = ("product_name", "sku", "unit_price", "total_price")
    autocomplete_fields = ("product", "variant")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number", "user", "status", "payment_status", "total", "created_at",
    )
    list_filter = ("status", "payment_status", "created_at")
    search_fields = ("order_number", "user__username", "user__email", "shipping_phone")
    autocomplete_fields = ("user", "coupon")
    readonly_fields = ("order_number", "created_at", "updated_at")
    inlines = [OrderItemInline]
    fieldsets = (
        (None, {"fields": ("order_number", "user", "status", "payment_status", "coupon")}),
        ("Totals", {"fields": ("subtotal", "discount_amount", "shipping_cost", "total")}),
        ("Shipping address", {
            "fields": (
                "shipping_recipient_name", "shipping_phone", "shipping_province",
                "shipping_city", "shipping_address", "shipping_postal_code",
                "shipping_unit", "shipping_building_number",
            ),
        }),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
