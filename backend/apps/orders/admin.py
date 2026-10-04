"""
Orders admin registration (Phase B - Store management).

The admin is the shop owner's day-to-day order desk:

* Status changes go through apps/orders/workflow.set_status, which
  enforces the transition DAG and restores stock exactly once when a
  paid order is cancelled. Invalid transitions raise ValidationError
  and NOTHING is saved.
* Every snapshot field (address, shipping method/window, totals,
  items, coupon) is read-only: orders must stay historically correct.
* Admin cannot create orders (they only come from checkout), so there
  is no "required snapshot field" problem on a create form.
* A printable shipping-label/invoice page and a CSV export action are
  provided for the owner.
"""
import csv

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from .models import Order, OrderItem
from .refunds import RefundError, finalize_refunded, validate_admin_refund_change
from .shipping import method_label as shipping_method_label
from .workflow import OrderWorkflowError, check_transition, set_status


class OrderItemInline(admin.TabularInline):
    """Read-only items snapshot -- never editable after checkout."""

    model = OrderItem
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("product", "variant", "product_name", "sku", "unit_price", "quantity", "total_price")
    readonly_fields = ("product", "variant", "product_name", "sku", "unit_price", "quantity", "total_price")
    autocomplete_fields = ()


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number", "user", "status", "payment_status", "total",
        "shipping_method_label", "stock_restored_badge", "refund_badge", "created_at",
    )
    # refund_status in the filter list is the owner's daily "which orders
    # still owe a refund?" view: «نیازمند بازپرداخت» (Phase C).
    list_filter = ("status", "payment_status", "refund_status", "created_at")

    @admin.display(description="روش ارسال")
    def shipping_method_label(self, obj):
        return shipping_method_label(obj.shipping_method)
    search_fields = ("order_number", "user__username", "user__email", "shipping_phone", "tracking_code")
    autocomplete_fields = ("user", "coupon")
    date_hierarchy = "created_at"
    readonly_fields = (
        # Gift-wrap values are checkout SNAPSHOTs (Part 2): visible in
        # admin but never editable after the fact.
        "gift_wrap", "gift_wrap_fee", "gift_message",
        "order_number", "created_at", "updated_at", "stock_restored_at",
        # Stamped by the system when a refund is recorded, never typed.
        "refunded_at",
        # Totals snapshot
        "subtotal", "discount_amount", "shipping_cost", "total",
        # Shipping address snapshot
        "shipping_recipient_name", "shipping_phone", "shipping_province",
        "shipping_city", "shipping_address", "shipping_postal_code",
        "shipping_unit", "shipping_building_number",
        # Shipping method + delivery window snapshot
        "shipping_method", "estimated_delivery_min", "estimated_delivery_max",
    )
    inlines = [OrderItemInline]
    actions = ["export_orders_csv"]
    change_form_template = "admin/orders/order_change_form.html"

    fieldsets = (
        (None, {"fields": ("order_number", "user", "status", "payment_status", "coupon")}),
        ("Fulfilment", {"fields": ("tracking_code", "stock_restored_at")}),
        ("Totals", {"fields": ("subtotal", "discount_amount", "shipping_cost", "total")}),
        ("Refund", {
            "fields": ("refund_status", "refund_amount", "refund_reference", "refunded_at"),
            "description": (
                "بازپرداخت وجه دستی است (از پنل درگاه انجام می‌شود). لغو یا مرجوع کردن "
                "سفارش پرداخت‌شده، آن را به‌صورت خودکار «نیازمند بازپرداخت» می‌کند. پس از "
                "انجام بازپرداخت در پنل درگاه، وضعیت را به «بازپرداخت شده» تغییر دهید و "
                "مرجع/یادداشت آن را در فیلد یادداشت اضافه کنید (بدون یادداشت ثبت نمی‌شود)."
            ),
        }),
        ("Shipping address", {
            "fields": (
                "shipping_recipient_name", "shipping_phone", "shipping_province",
                "shipping_city", "shipping_address", "shipping_postal_code",
                "shipping_unit", "shipping_building_number",
            ),
        }),
        ("Shipping method", {"fields": ("shipping_method", "estimated_delivery_min", "estimated_delivery_max")}),
        ("Gift wrapping (Part 2)", {"fields": ("gift_wrap", "gift_wrap_fee", "gift_message")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        # Orders only come from the checkout flow; admin manages existing ones.
        return False

    def stock_restored_badge(self, obj):
        if obj.stock_restored_at is None:
            return ""
        return format_html('<span title="{}">↩️</span>', "موجودی پس از لغو بازگردانده شده است")

    stock_restored_badge.short_description = ""

    def refund_badge(self, obj):
        if obj.refund_status == Order.RefundStatus.REQUIRED:
            return format_html('<span title="{}">💸</span>', "نیازمند بازپرداخت وجه")
        if obj.refund_status == Order.RefundStatus.REFUNDED:
            return format_html('<span title="{}">✅</span>', "بازپرداخت وجه انجام شده است")
        return ""

    refund_badge.short_description = "بازپرداخت"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/print/",
                self.admin_site.admin_view(self.print_view),
                name="orders_order_print",
            ),
        ]
        return custom + urls

    def print_view(self, request, pk):
        from apps.core.models import SiteSettings

        from . import shipping

        order = get_object_or_404(
            Order.objects.prefetch_related("items", "items__product", "items__variant"),
            pk=pk,
        )
        return TemplateResponse(
            request,
            "admin/orders/order_print.html",
            {
                "order": order,
                "opts": self.model._meta,
                "title": f"Print {order.order_number}",
                "shipping_method_label": shipping.method_label(order.shipping_method),
                "site": SiteSettings.load(),
            },
        )

    def save_model(self, request, obj, form, change):
        """
        Route status changes through the workflow so the DAG is enforced
        and stock restoration on cancel is exactly-once, and route refund
        bookkeeping changes (Phase C) through apps/orders/refunds.py.
        Validate BEFORE saving so an invalid transition persists nothing.
        """
        if not change:
            return super().save_model(request, obj, form, change)

        db_obj = Order.objects.get(pk=obj.pk)

        # --- Refund bookkeeping (validated pre-save, same fail-closed rule) ---
        refund_message = None
        if obj.refund_status != db_obj.refund_status:
            try:
                if obj.refund_status == Order.RefundStatus.REFUNDED:
                    # The owner typed their note into the journal textarea;
                    # finalize validates it was actually added, stamps
                    # refunded_at and moves payment_status PAID -> REFUNDED.
                    finalize_refunded(obj, db_obj)
                    refund_message = (
                        f"بازپرداخت وجه به مبلغ {obj.refund_amount:,} تومان ثبت شد."
                    )
                else:
                    validate_admin_refund_change(db_obj, obj.refund_status)
                    if obj.refund_status == Order.RefundStatus.REQUIRED and not obj.refund_amount:
                        # Manual flag with no amount: the sensible default is
                        # the full order total (what the customer paid).
                        obj.refund_amount = db_obj.total
            except RefundError as exc:
                raise ValidationError(str(exc))

        # --- Order status transition (existing workflow routing) --------------
        requested_status = obj.status
        if requested_status == db_obj.status:
            super().save_model(request, obj, form, change)
            if refund_message:
                self.message_user(request, refund_message, messages.INFO)
            return

        # Validate against the DB's current status but with the INCOMING
        # field values (e.g. a tracking code typed in this very save).
        try:
            check_transition(
                db_obj.status, requested_status, obj.tracking_code, obj.shipping_method
            )
        except OrderWorkflowError as exc:
            raise ValidationError(str(exc))

        # Persist everything except the status; set_status applies the
        # transition atomically (restores stock AND flags the refund as
        # required if this is a paid order being cancelled/returned).
        obj.status = db_obj.status
        super().save_model(request, obj, form, change)
        try:
            set_status(obj, requested_status)
        except OrderWorkflowError as exc:  # pragma: no cover - validated above
            raise ValidationError(str(exc))
        obj.refresh_from_db()

        if obj.status == Order.Status.CANCELLED and obj.stock_restored_at is not None:
            self.message_user(
                request,
                "سفارش لغو شد و موجودی کسرشدهٔ آن به کاتالوگ بازگشت.",
                messages.INFO,
            )
        if obj.refund_status == Order.RefundStatus.REQUIRED and db_obj.refund_status != Order.RefundStatus.REQUIRED:
            self.message_user(
                request,
                f"این سفارش نیازمند بازپرداخت وجه به مبلغ {obj.refund_amount:,} تومان است — "
                "بازپرداخت را از پنل درگاه انجام دهید و سپس اینجا ثبت کنید.",
                messages.WARNING,
            )
        if refund_message:
            self.message_user(request, refund_message, messages.INFO)

    @admin.action(description="خروجی CSV از سفارش‌های انتخاب‌شده")
    def export_orders_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        response["Content-Disposition"] = f'attachment; filename="orders-{stamp}.csv"'
        # UTF-8 BOM so Excel opens Persian text correctly.
        response.write("\ufeff")

        writer = csv.writer(response)
        writer.writerow([
            "order_number", "created_at", "customer", "phone", "status",
            "payment_status", "subtotal", "discount", "shipping_cost", "total",
            "shipping_method", "tracking_code", "gift_wrap",
            "refund_status", "refund_amount", "refunded_at",
        ])
        for order in queryset.select_related("user"):
            writer.writerow([
                order.order_number,
                order.created_at.isoformat(),
                order.shipping_recipient_name,
                order.shipping_phone,
                order.status,
                order.payment_status,
                order.subtotal,
                order.discount_amount,
                order.shipping_cost,
                order.total,
                shipping_method_label(order.shipping_method),
                order.tracking_code,
                "بله" if order.gift_wrap else "خیر",
                order.refund_status,
                order.refund_amount,
                order.refunded_at.isoformat() if order.refunded_at else "",
            ])
        return response
