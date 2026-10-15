"""
NotificationLog admin (Phase D - Notifications).

Strictly READ-ONLY, same reasoning as PaymentAdmin: this table is an
audit trail of what the system told customers and what providers
answered. Editing or deleting rows here would falsify that record, and
nothing legitimate ever needs it -- resends happen by re-triggering the
event, not by hand-editing logs.
"""
from django.contrib import admin

from apps.adminui.admin_dates import jalali_column

from .models import NotificationLog
from .services import EVENT_LABELS


class NotificationEventFilter(admin.AllValuesFieldListFilter):
    """The stored values are machine codes («order_confirmed»); the sidebar
    must offer the Persian labels.

    The event field deliberately has NO ``choices``: new events are added
    by code, and a DB-level choice list would reject a code the log has
    never seen. Labelling is therefore a display concern.
    """

    def choices(self, changelist):
        for choice in super().choices(changelist):
            display = choice.get("display")
            if display in EVENT_LABELS:
                choice = dict(choice, display=EVENT_LABELS[display])
            yield choice


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        jalali_column("created_at", "زمان", with_time=True),
        "event_label", "channel", "status",
        "recipient_masked", "order_link", "provider_message_id",
    )
    list_filter = (("event", NotificationEventFilter), "channel", "status", "created_at")
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

    @admin.display(description="رویداد", ordering="event")
    def event_label(self, obj):
        """The stored value is a machine code (``order_confirmed``); the
        owner reads Persian."""
        return EVENT_LABELS.get(obj.event, obj.event)

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
