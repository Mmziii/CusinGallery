"""
NotificationLog admin (Phase D - Notifications).

Strictly READ-ONLY, same reasoning as PaymentAdmin: this table is an
audit trail of what the system told customers and what providers
answered. Editing or deleting rows here would falsify that record, and
nothing legitimate ever needs it -- resends happen by re-triggering the
event, not by hand-editing logs.
"""
from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "event", "channel", "status",
        "recipient_masked", "order_link", "provider_message_id",
    )
    list_filter = ("event", "channel", "status", "created_at")
    search_fields = (
        "order__order_number", "recipient_masked",
        "provider_message_id", "error",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = tuple(
        f.name for f in NotificationLog._meta.concrete_fields
    )
    list_select_related = ("order",)

    def order_link(self, obj):
        return obj.order.order_number if obj.order_id else "—"

    order_link.short_description = "سفارش"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # False even for superusers: view-only, by design (module docstring).
        return False

    def has_delete_permission(self, request, obj=None):
        return False
