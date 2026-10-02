"""
Payments admin registration (Phase 7 - Payment architecture).

Payments are financial audit records: everything here is effectively
read-only. Support can inspect and filter attempts; actually changing a
payment's status (e.g. after reconciling with the PSP) is a deliberate
manual database action, not an admin checkbox -- a misclick here must
never be able to mark money as received or re-trigger inventory effects.
"""
from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "order_number", "customer", "amount", "gateway",
        "status", "paid_at", "created_at",
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
