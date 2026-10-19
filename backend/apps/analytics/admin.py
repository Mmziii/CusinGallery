"""Admin registration for the raw event log.

Deliberately read-only and parked in the «سایر / پیشرفته» sidebar bucket:
the owner's daily entry point is the «گزارش‌ها و تحلیل» page
(apps/analytics/admin_views.py), not a table of millions of rows. The
changelist exists so a support question ("was this product viewed?") can
be answered, and so the ``analytics.view_event`` permission has a model
behind it.
"""
from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at_jalali", "event_type_display", "product", "user",
        "search_query", "province_city",
    )
    list_filter = ("event_type",)
    # Session keys are anonymous, but exposing them in a searchable admin
    # column buys nothing for the owner -- keep the log about the events.
    search_fields = ("search_query", "product__name", "user__phone", "user__username")
    readonly_fields = (
        "event_type", "product", "order", "user", "session_key",
        "search_query", "search_results", "province", "city", "created_at",
    )
    date_hierarchy = "created_at"
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="زمان", ordering="created_at")
    def created_at_jalali(self, obj):
        from apps.adminui.jalali import format_jalali_datetime

        return format_jalali_datetime(obj.created_at)

    @admin.display(description="نوع رویداد", ordering="event_type")
    def event_type_display(self, obj):
        return obj.get_event_type_display()

    @admin.display(description="استان / شهر")
    def province_city(self, obj):
        parts = [part for part in (obj.province, obj.city) if part]
        return " / ".join(parts) or "—"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product", "user", "order")
