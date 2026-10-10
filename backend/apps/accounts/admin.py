"""
Accounts admin registration.

Registers User with a small extension of Django's built-in UserAdmin --
surfacing `phone` (Phase 2) and making it searchable (Phase 3) -- and
registers Address. Passwords are never exposed: DjangoUserAdmin already
renders the password field as a one-way hash display
(ReadOnlyPasswordHashField), inherited here unmodified.

Admin-panel work (B5) adds, purely additively:
* an orders-count column (single annotate, no N+1) and a Jalali
  join-date column to the user list;
* a read-only customer summary header on the change page (orders count,
  total paid, last order, default address, SMS consent) linking to the
  customer's orders in the orders changelist.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.adminui.jalali import format_jalali
from apps.adminui.templatetags.adminui_extras import (
    group_thousands,
    to_fa_digits,
)

from .models import Address, User


class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Contact", {"fields": ("phone",)}),
    )
    list_display = DjangoUserAdmin.list_display + (
        "phone", "orders_count", "date_joined_jalali",
    )
    search_fields = DjangoUserAdmin.search_fields + ("phone",)
    change_form_template = "admin/accounts/user_change_form.html"

    def get_queryset(self, request):
        # One grouped COUNT for the whole page -- the orders column must
        # not run a query per row.
        return super().get_queryset(request).annotate(
            _orders_count=Count("orders", distinct=True),
        )

    @admin.display(description="سفارش‌ها", ordering="_orders_count")
    def orders_count(self, obj):
        count = getattr(obj, "_orders_count", obj.orders.count())
        return format_html(
            '<a class="cusin-badge off" href="{}" title="مشاهدهٔ سفارش‌های این مشتری">{}</a>',
            f"{reverse('admin:orders_order_changelist')}?user__id__exact={obj.pk}",
            to_fa_digits(group_thousands(count)),
        )

    @admin.display(description="تاریخ عضویت", ordering="date_joined")
    def date_joined_jalali(self, obj):
        local = timezone.localtime(obj.date_joined)
        return format_html(
            '<span class="cusin-nowrap" title="{}">{}</span>',
            local.strftime("%Y-%m-%d %H:%M"),
            format_jalali(local),
        )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = dict(extra_context or {})
        if object_id is not None:
            user_obj = self.get_object(request, object_id)
            if user_obj is not None:
                extra_context.update(self._customer_summary(user_obj))
        return super().changeform_view(request, object_id, form_url, extra_context)

    def _customer_summary(self, user_obj):
        aggregates = user_obj.orders.aggregate(
            orders_count=Count("pk"),
            total_paid=Sum("total", filter=Q(payment_status="paid")),
        )
        last_order = user_obj.orders.order_by("-created_at").first()
        default_address = user_obj.addresses.filter(is_default=True).first()
        return {
            "cusin_customer_summary": {
                "orders_count": aggregates["orders_count"] or 0,
                "total_paid": aggregates["total_paid"] or 0,
                "last_order": last_order,
                "default_address": default_address,
                "sms_consent": bool(getattr(user_obj, "marketing_sms_consent", False)),
                "orders_url": (
                    f"{reverse('admin:orders_order_changelist')}"
                    f"?user__id__exact={user_obj.pk}"
                ),
            },
        }


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("recipient_name", "user", "city", "province", "is_default", "created_at")
    list_filter = ("is_default", "province")
    search_fields = ("recipient_name", "phone", "city", "postal_code", "user__username", "user__email")
    autocomplete_fields = ("user",)


admin.site.register(User, UserAdmin)
