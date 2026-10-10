"""
Payments admin registration (Phase 7 - Payment architecture).

Payments are financial audit records: everything here is effectively
read-only. Support can inspect and filter attempts; actually changing a
payment's status (e.g. after reconciling with the PSP) is a deliberate
manual database action, not an admin checkbox -- a misclick here must
never be able to mark money as received or re-trigger inventory effects.
"""
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from apps.adminui.jalali import format_jalali_datetime
from apps.adminui.templatetags.adminui_extras import toman_filter

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    # Same information as before; the display-only columns are upgraded
    # (B2/A4): Jalali timestamps with the Gregorian value in the tooltip,
    # Persian-digit amounts and a status badge. Sorting is preserved via
    # admin_order_field; inputs, filters and the read-only stance are
    # untouched.
    list_display = (
        "id", "order_number", "customer", "amount_fa", "gateway",
        "status_badge", "paid_at_jalali", "created_at_jalali",
    )

    @admin.display(description="مبلغ", ordering="amount")
    def amount_fa(self, obj):
        return format_html(
            '<span class="cusin-nowrap" title="{}">{}</span>',
            f"{obj.amount:,}", toman_filter(obj.amount),
        )

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj):
        css = {
            Payment.Status.SUCCESS: "paid",
            Payment.Status.FAILED: "failed",
            Payment.Status.CANCELLED: "unpaid",
        }.get(obj.status, "pending")
        return format_html(
            '<span class="cusin-badge pay-{}">{}</span>', css, obj.get_status_display(),
        )

    @admin.display(description="زمان پرداخت", ordering="paid_at")
    def paid_at_jalali(self, obj):
        if obj.paid_at is None:
            return format_html('<span class="cusin-muted">—</span>')
        local = timezone.localtime(obj.paid_at)
        return format_html(
            '<span class="cusin-nowrap" title="{}">{}</span>',
            local.strftime("%Y-%m-%d %H:%M"), format_jalali_datetime(local),
        )

    @admin.display(description="زمان ثبت", ordering="created_at")
    def created_at_jalali(self, obj):
        local = timezone.localtime(obj.created_at)
        return format_html(
            '<span class="cusin-nowrap" title="{}">{}</span>',
            local.strftime("%Y-%m-%d %H:%M"), format_jalali_datetime(local),
        )
    list_filter = ("status", "gateway", "created_at")
    search_fields = (
        "order__order_number", "order__user__username", "order__user__email",
        "gateway_transaction_id", "gateway_ref_id",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    readonly_fields = (
        "order", "amount", "gateway", "gateway_transaction_id",
        "gateway_ref_id", "card_pan", "card_pan_hash",
        "failure_reason", "status", "paid_at",
        "created_at", "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("order", "amount", "status")}),
        ("Gateway", {
            "fields": (
                "gateway", "gateway_transaction_id", "gateway_ref_id",
                # Receipt data captured from the gateway's verify answer
                # (Phase C): masked card number + its fingerprint, for
                # support ("which card paid for this?") and reconciliation
                # against the PSP panel. Never full card data.
                "card_pan", "card_pan_hash",
                "failure_reason",
            ),
        }),
        ("Timestamps", {"fields": ("paid_at", "created_at", "updated_at")}),
    )

    def order_number(self, obj):
        return obj.order.order_number

    def customer(self, obj):
        return obj.order.user.get_full_name() or obj.order.user.username

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # PROTECT on Payment.order already refuses to delete an order with
        # payments; deleting payment rows themselves would punch holes in
        # the audit trail, so it's off here too.
        return False
