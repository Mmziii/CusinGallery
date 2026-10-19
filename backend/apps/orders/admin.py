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
import datetime as dt

from django import forms
from django.conf import settings as django_settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.adminui.admin_dates import jalali_date as _jalali_date, jalali_range
from apps.adminui.jalali import format_jalali_datetime
from apps.adminui.search import NormalizedSearchMixin
from apps.adminui.templatetags.adminui_extras import to_fa_digits, toman_filter
from apps.payments.models import Payment

from .models import Order, OrderItem
from .refunds import RefundError, finalize_refunded, validate_admin_refund_change
from .shipping import method_label as shipping_method_label
from .workflow import (
    OrderWorkflowError,
    allowed_next_statuses,
    check_transition,
    payment_block_reason,
    set_status,
)

# Happy-path fulfilment flow, in DAG order (used by the change-page
# status stepper and to keep quick-action buttons deterministically
# ordered).
FLOW_STATUSES = [
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.PROCESSING,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
]

def abandoned_unpaid_q(now=None):
    """Orders the customer walked away from: never paid, still open, and
    older than ORDER_ABANDONED_UNPAID_AFTER_HOURS.

    They are real rows (and the refund/expiry cron still sees them), so
    they are HIDDEN from the default admin list rather than deleted --
    the owner's work queue should be the orders that need a decision.
    """
    hours = getattr(django_settings, "ORDER_ABANDONED_UNPAID_AFTER_HOURS", 24) or 24
    cutoff = (now or timezone.now()) - dt.timedelta(hours=max(int(hours), 1))
    return (
        Q(payment_status__in=[
            Order.PaymentStatus.UNPAID,
            Order.PaymentStatus.PENDING,
            Order.PaymentStatus.FAILED,
        ])
        & Q(status=Order.Status.PENDING)
        & Q(created_at__lt=cutoff)
    )


# Queue filter/tab definitions: (key, Persian label, sprite icon).
# Purely additive views over existing columns -- every tab maps to the
# same predicates the dashboard "needs action" cards use.
ORDER_QUEUES = (
    ("awaiting_payment", "در انتظار پرداخت", "hourglass"),
    # A paid order stays «در انتظار تأیید» until the OWNER confirms it:
    # that queue is the owner's real inbox.
    ("awaiting_confirmation", "پرداخت‌شده‌های در انتظار تأیید", "bell"),
    ("paid_to_process", "تأیید‌شدهٔ در حال آماده‌سازی", "box"),
    ("shipped", "ارسال‌شده", "truck"),
    ("delivered", "تحویل‌شده", "check"),
    ("cancelled_returned", "لغو/مرجوع", "x"),
    ("needs_refund", "نیازمند بازپرداخت", "refund"),
    ("pickup_waiting", "حضوریِ تحویل‌نشده", "store"),
    ("abandoned", "سفارش‌های رهاشده", "hourglass"),
)

QUEUE_FILTERS = {
    "awaiting_payment": Q(payment_status__in=[
        Order.PaymentStatus.UNPAID, Order.PaymentStatus.PENDING,
    ], status__in=[
        Order.Status.PENDING, Order.Status.CONFIRMED,
        Order.Status.PROCESSING, Order.Status.SHIPPED,
    ]),
    "awaiting_confirmation": Q(
        payment_status=Order.PaymentStatus.PAID, status=Order.Status.PENDING,
    ),
    "paid_to_process": Q(payment_status=Order.PaymentStatus.PAID, status__in=[
        Order.Status.CONFIRMED, Order.Status.PROCESSING,
    ]),
    "shipped": Q(status=Order.Status.SHIPPED),
    "delivered": Q(status=Order.Status.DELIVERED),
    "cancelled_returned": Q(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED]),
    "needs_refund": Q(refund_status=Order.RefundStatus.REQUIRED),
    # Not gone, just hidden from the DEFAULT list -- see
    # OrderAdmin.get_queryset. One click away, and the cron cancels them.
    # A callable because the cutoff is "now minus N hours", not a constant.
    "abandoned": abandoned_unpaid_q,
    "pickup_waiting": Q(
        payment_status=Order.PaymentStatus.PAID,
        shipping_method="pickup",
        status__in=[
            Order.Status.PENDING, Order.Status.CONFIRMED,
            Order.Status.PROCESSING, Order.Status.SHIPPED,
        ],
    ),
}

# Owner-facing wording for the outcome of the LAST gateway attempt. The
# raw Payment.Status labels describe the PSP record («لغو شده»); on an
# order the owner wants to know what the CUSTOMER did at the gateway
# («لغو توسط مشتری»).
LAST_ATTEMPT_PHRASES = {
    Payment.Status.SUCCESS: "موفق",
    Payment.Status.FAILED: "ناموفق",
    Payment.Status.CANCELLED: "لغو توسط مشتری",
    Payment.Status.PENDING: "در انتظار نتیجه از درگاه",
}

# Quick-action button presentation per target status.
QUICK_ACTION_META = {
    Order.Status.CONFIRMED: ("check", ""),
    Order.Status.PROCESSING: ("sliders", ""),
    Order.Status.SHIPPED: ("truck", ""),
    Order.Status.DELIVERED: ("store", ""),
    Order.Status.CANCELLED: ("x", "danger"),
    Order.Status.RETURNED: ("refund", "danger"),
}


class OrderQueueFilter(admin.SimpleListFilter):
    """Additive «صف کاری» filter powering the changelist tabs (B3a).

    Existing filters (status/payment/refund/created_at) stay untouched;
    GET params they use keep working exactly as before.
    """

    title = "صف کاری"
    parameter_name = "queue"

    def lookups(self, request, model_admin):
        return [(key, label) for key, label, _icon in ORDER_QUEUES]

    def queryset(self, request, queryset):
        predicate = QUEUE_FILTERS.get(self.value())
        if predicate is None:
            return queryset
        # An entry may be a callable -- the "abandoned" cutoff depends on
        # the current time, so it cannot be a frozen Q object.
        return queryset.filter(predicate() if callable(predicate) else predicate)


def _jalali_stamp(value) -> str:
    """Jalali date and time in the active timezone, Persian digits (B2 helper)."""
    if value is None:
        return "—"
    return format_jalali_datetime(timezone.localtime(value))


def _whatsapp_link(phone: str) -> str:
    """Best-effort wa.me link for an Iranian phone snapshot ('' if unknown)."""
    digits = "".join(ch for ch in phone or "" if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "98" + digits[1:]
    elif not digits.startswith("98"):
        return ""
    return f"https://wa.me/{digits}"


class OrderItemInline(admin.TabularInline):
    """Read-only items snapshot -- never editable after checkout."""

    model = OrderItem
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("product", "variant", "product_name", "sku", "unit_price", "quantity", "total_price")
    readonly_fields = ("product", "variant", "product_name", "sku", "unit_price", "quantity", "total_price")
    autocomplete_fields = ()


class OrderStatusSelect(forms.Select):
    """
    The status <select> of the order change form (Audit 19 item 6).

    The owner's report: on an UNPAID order the select still listed
    «تأیید شده» and every later status, even though saving them is refused by
    the workflow. Being shown an action that cannot succeed is a trap, so the
    widget renders:

      * only the statuses that are actually reachable -- the order's CURRENT
        status (a plain save must stay possible) and the transitions both the
        DAG and the payment rule allow;
      * the transitions the DAG allows but the payment rule forbids as
        ``disabled`` options, each carrying its Persian reason as a ``title``
        -- never silently hidden, because "why is «تأیید شده» missing?" is
        its own support call.

    The server-side rule is untouched: apps/orders/workflow.validate_transition
    (called from save_model under the row lock) still refuses everything this
    list does not offer.
    """

    def __init__(self, attrs=None, disabled_options=None, **kwargs):
        super().__init__(attrs, **kwargs)
        self.disabled_options = list(disabled_options or [])

    def optgroups(self, name, value, attrs=None):
        groups = super().optgroups(name, value, attrs)
        if not groups or not self.disabled_options:
            return groups
        index = len(groups[0][1])
        for entry in self.disabled_options:
            option = self.create_option(name, entry["value"], entry["label"], False, index)
            option["attrs"]["disabled"] = True
            option["attrs"]["title"] = entry["reason"]
            groups[0][1].append(option)
            index += 1
        return groups


class OrderAdminForm(forms.ModelForm):
    """
    Order change form with a status field that only offers what will be
    accepted (Audit 19 item 6). Everything else is stock ModelForm behaviour.
    """

    class Meta:
        model = Order
        fields = "__all__"
        widgets = {"status": OrderStatusSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        order = self.instance
        field = self.fields.get("status")
        if field is None or order is None or not order.pk:
            return

        reachable = []
        blocked = []
        for status in Order.Status.values:
            if status == order.status:
                reachable.append(status)
                continue
            if status not in allowed_next_statuses(order.status):
                continue
            reason = payment_block_reason(order, status)
            if reason:
                blocked.append(
                    {"value": status, "label": Order.Status(status).label, "reason": reason}
                )
            else:
                reachable.append(status)

        field.choices = [(status, Order.Status(status).label) for status in reachable]
        # The disabled extras live on the widget only: they are NOT valid
        # choices, so a crafted POST that sends one is rejected by the field
        # before the workflow even sees it.
        field.widget.disabled_options = blocked

        hints = []
        if blocked:
            hints.append(
                "گزینه‌های خاکستری (غیرفعال) در وضعیت فعلی این سفارش مجاز نیستند؛ "
                + " ".join(f"«{entry['label']}»: {entry['reason']}" for entry in blocked)
            )
        hints.append(
            "فقط انتقال‌های مجاز گردش کار نمایش داده می‌شوند؛ تغییرهای دیگر توسط "
            "سیستم رد می‌شوند."
        )
        field.help_text = " ".join(hints)


@admin.register(Order)
class OrderAdmin(NormalizedSearchMixin, admin.ModelAdmin):
    # Preserve every operational value and its sort key, but present the
    # order number compactly and put the amount's currency unit in its header.
    list_display = (
        "order_number_cell", "customer_cell", "status_badge", "payment_badge",
        "last_attempt_cell", "total_fa",
        "shipping_method_cell", "stock_restored_badge", "refund_badge",
        "created_at_jalali",
    )
    list_display_links = ("order_number_cell",)
    # refund_status in the filter list is the owner's daily "which orders
    # still owe a refund?" view: «نیازمند بازپرداخت» (Phase C).
    # OrderQueueFilter (B3a) is purely additive and powers the tabs.
    list_filter = (OrderQueueFilter, "status", "payment_status", "refund_status", "created_at")
    change_list_template = "admin/orders/order_change_list.html"
    # Audit 19 item 6: the status select offers only reachable statuses (see
    # OrderAdminForm); the workflow's server-side rule is unchanged.
    form = OrderAdminForm

    @admin.display(description="شماره", ordering="order_number")
    def order_number_cell(self, obj):
        return format_html(
            '<span class="cusin-order-number" dir="ltr" title="{}">{}</span>',
            obj.order_number,
            obj.order_number,
        )

    @admin.display(description="مشتری", ordering="user__last_name")
    def customer_cell(self, obj):
        """Name and mobile, not a login name.

        The owner recognises a customer as «زهرا احمدی / ۰۹۱۲…» and it is
        the mobile that gets dialled when a delivery needs confirming. The
        account's username is an internal artifact -- for phone-only
        accounts it is just the number typed again.
        """
        user = getattr(obj, "user", None)
        if user is None:
            return "—"
        name = (user.get_full_name() or "").strip() or user.username
        # The order's own shipping phone is the one the courier needs; the
        # account phone is the fallback when the customer ordered for
        # someone else.
        mobile = obj.shipping_phone or getattr(user, "phone", "") or ""
        # Task 4: name on one line, phone (Persian digits, isolated LTR)
        # on a second muted line; both ellipsize inside the cell with
        # the full value in the title tooltip (theme.css section 24).
        mobile_fa = to_fa_digits(str(mobile)) if mobile else "—"
        return format_html(
            '<span class="cusin-customer">'
            '<span class="cusin-customer__name" title="{}">{}</span>'
            '<bdi class="cusin-customer__phone" dir="ltr" title="{}">{}</bdi>'
            "</span>",
            name,
            name,
            mobile_fa,
            mobile_fa,
        )

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span class="cusin-badge st-{}">{}</span>',
            obj.status, obj.get_status_display(),
        )

    @admin.display(description="پرداخت", ordering="payment_status")
    def payment_badge(self, obj):
        return format_html(
            '<span class="cusin-badge pay-{}">{}</span>',
            obj.payment_status, obj.get_payment_status_display(),
        )

    # --- last gateway attempt (what the CUSTOMER did at the gateway) ---

    @staticmethod
    def last_payment_attempt(obj):
        """The most recent Payment row, or None. Uses the prefetch set up
        in get_queryset when there is one (no N+1 on the changelist)."""
        cached = getattr(obj, "recent_payments", None)
        if cached is not None:
            return cached[0] if cached else None
        return obj.payments.order_by("-created_at").first()

    @admin.display(description="آخرین تلاش پرداخت")
    def last_attempt_cell(self, obj):
        payment = self.last_payment_attempt(obj)
        if payment is None:
            return format_html('<span class="cusin-muted">—</span>')
        phrase = LAST_ATTEMPT_PHRASES.get(payment.status, payment.get_status_display())
        when = timezone.localtime(payment.created_at)
        when_fa = format_jalali_datetime(when)
        return format_html(
            '<span class="cusin-attempt attempt-{}" title="{} — {}">'
            '<span class="cusin-attempt__label">{}</span>'
            '<small class="cusin-muted">{}</small></span>',
            payment.status,
            phrase,
            when_fa,
            phrase,
            when_fa,
        )

    @admin.display(description="مبلغ (تومان)", ordering="total")
    def total_fa(self, obj):
        # Keep the copyable ASCII figure in the title. The unit is in the
        # compact heading, so each Persian-digit amount stays on one line.
        return format_html(
            '<span class="cusin-order-amount" dir="ltr" title="{}">{}</span>',
            f"{obj.total:,}",
            toman_filter(obj.total, suffix=""),
        )

    @admin.display(description="تاریخ", ordering="created_at")
    def created_at_jalali(self, obj):
        local = timezone.localtime(obj.created_at)
        return format_html(
            '<span class="cusin-order-date" title="{}">{}</span>',
            local.strftime("%Y-%m-%d %H:%M"),
            format_jalali_datetime(local),
        )

    _SHIP_ICONS = {"standard": "truck", "express": "zap", "pickup": "store"}

    @admin.display(description="روش", ordering="shipping_method")
    def shipping_method_cell(self, obj):
        icon = self._SHIP_ICONS.get(obj.shipping_method, "truck")
        label = shipping_method_label(obj.shipping_method)
        return format_html(
            '<span class="cusin-ship" title="{}">'
            '<svg class="cusin-icon" aria-hidden="true"><use href="#cusin-i-{}"></use></svg>'
            "{}</span>",
            label, icon, label,
        )

    @admin.display(description="روش ارسال")
    def shipping_method_label(self, obj):
        return shipping_method_label(obj.shipping_method)

    @admin.display(description="تاریخ ایجاد")
    def created_at_detail(self, obj):
        return _jalali_stamp(obj.created_at)

    @admin.display(description="تاریخ ویرایش")
    def updated_at_detail(self, obj):
        return _jalali_stamp(obj.updated_at)

    @admin.display(description="زودترین تاریخ تحویل")
    def estimated_delivery_min_detail(self, obj):
        # Read-only, so Django would otherwise render it with the fa
        # locale's Gregorian DATE_FORMAT («۱۸ اکتبر ۲۰۲۶»).
        return _jalali_date(obj.estimated_delivery_min)

    @admin.display(description="دیرترین تاریخ تحویل")
    def estimated_delivery_max_detail(self, obj):
        return _jalali_date(obj.estimated_delivery_max)

    @admin.display(description="بازهٔ تحویل")
    def delivery_window(self, obj):
        """«۱۴۰۵/۰۷/۲۶ تا ۱۴۰۵/۰۷/۲۸» -- one date when the window is a day."""
        return jalali_range(obj.estimated_delivery_min, obj.estimated_delivery_max)
    search_fields = ("order_number", "user__username", "user__email", "shipping_phone", "tracking_code")
    autocomplete_fields = ("user", "coupon")
    date_hierarchy = "created_at"
    readonly_fields = (
        # Gift-wrap values are checkout SNAPSHOTs (Part 2): visible in
        # admin but never editable after the fact.
        "gift_wrap", "gift_wrap_fee", "gift_message",
        "order_number", "created_at_detail", "updated_at_detail", "stock_restored_at",
        # Stamped by the system when a refund is recorded, never typed.
        "refunded_at",
        # Totals snapshot
        "subtotal", "discount_amount", "shipping_cost", "total",
        # Shipping address snapshot
        "shipping_recipient_name", "shipping_phone", "shipping_province",
        "shipping_city", "shipping_address", "shipping_postal_code",
        "shipping_unit", "shipping_building_number",
        # Shipping method (shown as its Persian label) + delivery window snapshot
        "shipping_method_label", "estimated_delivery_min_detail", "estimated_delivery_max_detail",
    )
    inlines = [OrderItemInline]
    actions = ["export_orders_csv", "export_orders_xlsx"]
    change_form_template = "admin/orders/order_change_form.html"

    fieldsets = (
        (None, {"fields": ("order_number", "user", "status", "payment_status", "coupon")}),
        ("ارسال و پیگیری", {"fields": ("tracking_code", "stock_restored_at")}),
        ("جمع‌ها", {"fields": ("subtotal", "discount_amount", "shipping_cost", "total")}),
        ("بازپرداخت", {
            "fields": ("refund_status", "refund_amount", "refund_reference", "refunded_at"),
            "description": (
                "بازپرداخت وجه دستی است (از پنل درگاه انجام می‌شود). لغو یا مرجوع کردن "
                "سفارش پرداخت‌شده، آن را به‌صورت خودکار «نیازمند بازپرداخت» می‌کند. پس از "
                "انجام بازپرداخت در پنل درگاه، وضعیت را به «بازپرداخت شده» تغییر دهید و "
                "مرجع/یادداشت آن را در فیلد یادداشت اضافه کنید (بدون یادداشت ثبت نمی‌شود)."
            ),
        }),
        ("نشانی ارسال", {
            "fields": (
                "shipping_recipient_name", "shipping_phone", "shipping_province",
                "shipping_city", "shipping_address", "shipping_postal_code",
                "shipping_unit", "shipping_building_number",
            ),
        }),
        ("روش ارسال", {"fields": ("shipping_method_label", "estimated_delivery_min_detail", "estimated_delivery_max_detail")}),
        ("بسته‌بندی هدیه", {"fields": ("gift_wrap", "gift_wrap_fee", "gift_message")}),
        ("زمان‌ها", {"fields": ("created_at_detail", "updated_at_detail")}),
    )

    # --- default work queue -------------------------------------------
    # GET params that mean "the owner asked for something specific", i.e.
    # stop hiding the abandoned unpaid orders.
    _EXPLICIT_VIEW_PARAMS = (
        "queue", "q", "all", "status__exact", "payment_status__exact",
        "refund_status__exact", "e", "o",
    )

    @classmethod
    def _hides_abandoned(cls, request) -> bool:
        """True on the DEFAULT list (no filter, no search, no tab)."""
        params = getattr(request, "GET", None)
        if params is None:
            return False
        if params.get("all") == "1":
            return False
        for name in cls._EXPLICIT_VIEW_PARAMS:
            if params.get(name):
                return False
        return not any(key.startswith("created_at") for key in params)

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("user").prefetch_related(
            Prefetch(
                "payments",
                queryset=Payment.objects.order_by("-created_at"),
                to_attr="recent_payments",
            )
        )
        if self._hides_abandoned(request):
            queryset = queryset.exclude(abandoned_unpaid_q())
        return queryset

    def has_add_permission(self, request):
        # Orders only come from the checkout flow; admin manages existing ones.
        return False

    def stock_restored_badge(self, obj):
        if obj.stock_restored_at is None:
            return ""
        return format_html('<span title="{}">بازگشت موجودی</span>', "موجودی پس از لغو بازگردانده شده است")

    stock_restored_badge.short_description = ""

    def refund_badge(self, obj):
        if obj.refund_status == Order.RefundStatus.REQUIRED:
            return format_html(
                '<span class="cusin-badge ref-required" title="{}">نیازمند بازپرداخت</span>',
                "نیازمند بازپرداخت وجه",
            )
        if obj.refund_status == Order.RefundStatus.REFUNDED:
            return format_html(
                '<span class="cusin-badge ref-refunded" title="{}">بازپرداخت شده</span>',
                "بازپرداخت وجه انجام شده است",
            )
        return ""

    refund_badge.short_description = "بازپرداخت"

    # ------------------------------------------------------------------
    # Changelist tabs (B3a)
    # ------------------------------------------------------------------
    def changelist_view(self, request, extra_context=None):
        extra_context = dict(extra_context or {})
        extra_context["queue_tabs"] = self._queue_tabs(request)
        extra_context.update(self._hidden_abandoned_context(request))
        return super().changelist_view(request, extra_context=extra_context)

    def _hidden_abandoned_context(self, request) -> dict:
        """How many abandoned unpaid orders the default list is hiding, and
        the link that shows them. Nothing is ever unreachable."""
        if not self._hides_abandoned(request):
            return {}
        hidden = (
            super().get_queryset(request).filter(abandoned_unpaid_q()).count()
        )
        if not hidden:
            return {}
        params = request.GET.copy()
        params["all"] = "1"
        return {
            "hidden_abandoned_count": hidden,
            "hidden_abandoned_url": f"{request.path}?{params.urlencode()}",
        }

    def _queue_tabs(self, request):
        """One conditional-aggregate query for every tab count.

        Counts run over the UNFILTERED queryset on purpose: the default
        list hides abandoned unpaid orders, but their tab must still show
        how many there are -- a hidden count is how work gets lost.
        """
        queryset = super().get_queryset(request)
        aggregate = {"all": Count("pk")}
        for key, _label, _icon in ORDER_QUEUES:
            predicate = QUEUE_FILTERS[key]
            aggregate[key] = Count(
                "pk", filter=predicate() if callable(predicate) else predicate
            )
        counts = queryset.aggregate(**aggregate)

        # Tab links keep every other active GET param (search, other
        # filters) and only swap the queue -- so tabs compose with the
        # filters the owner already uses.
        params = request.GET.copy()
        params.pop("queue", None)
        base_query = params.urlencode()
        prefix = f"{request.path}?{base_query}&" if base_query else f"{request.path}?"
        plain = f"{request.path}?{base_query}" if base_query else request.path

        tabs = [{
            "key": "all", "label": "همه", "icon": "grid",
            "count": counts["all"], "url": plain,
            "active": not request.GET.get("queue"),
        }]
        active_queue = request.GET.get("queue")
        for key, label, icon in ORDER_QUEUES:
            tabs.append({
                "key": key, "label": label, "icon": icon,
                "count": counts[key], "url": f"{prefix}queue={key}",
                "active": active_queue == key,
            })
        return tabs

    # ------------------------------------------------------------------
    # Change-page summary header + quick actions (B3b / B3c)
    # ------------------------------------------------------------------
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = dict(extra_context or {})
        if object_id is not None:
            order = self.get_object(request, object_id)
            if order is not None:
                extra_context.update(self._summary_context(request, order))
        return super().changeform_view(request, object_id, form_url, extra_context)

    def _summary_context(self, request, order):
        from . import shipping as shipping_module

        items = (
            order.items
            .select_related("product", "variant")
            .prefetch_related("product__images")
            .all()
        )
        summary_items = [{
            "item": item,
            "image": item.product.images.first() if item.product_id else None,
        } for item in items]

        # Status stepper: the happy path with done/current markers;
        # terminal states (cancelled/returned) render a chip instead.
        steps = []
        if order.status in FLOW_STATUSES:
            current_index = FLOW_STATUSES.index(order.status)
            for index, status in enumerate(FLOW_STATUSES):
                state = "current" if index == current_index else ("done" if index < current_index else "todo")
                steps.append({
                    "key": status, "label": Order.Status(status).label, "state": state,
                })
        terminal = None
        if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED):
            terminal = {
                "key": order.status,
                "label": Order.Status(order.status).label,
            }

        # Quick status buttons: ONLY the transitions BOTH the DAG and the
        # payment rule allow, in DAG order. An unpaid order therefore shows
        # «لغو شده» and nothing else (it cannot be confirmed, processed,
        # shipped or delivered until the money is in -- see
        # apps/orders/workflow.py).
        allowed = allowed_next_statuses(order.status)
        quick_allowed = []
        quick_blocked = []
        for status in FLOW_STATUSES + [Order.Status.RETURNED, Order.Status.CANCELLED]:
            if status not in allowed:
                continue
            blocked = payment_block_reason(order, status)
            if blocked:
                quick_blocked.append({
                    "value": status, "label": Order.Status(status).label,
                    "reason": blocked,
                })
                continue
            icon, tone = QUICK_ACTION_META.get(status, ("check", ""))
            quick_allowed.append({
                "value": status, "label": Order.Status(status).label,
                "icon": icon, "tone": tone,
            })
        # The single sentence the owner needs on an unpaid order -- and only
        # while there is still something to decide. On a cancelled or
        # returned order the sentence is noise AND wrong: there is nothing
        # left to cancel, so «فقط می‌توان آن را لغو کرد» describes an
        # action the page no longer offers.
        unpaid_warning = ""
        if (
            order.payment_status != Order.PaymentStatus.PAID
            and order.status == Order.Status.PENDING
        ):
            unpaid_warning = (
                "پرداخت نشده — این سفارش هنوز پرداخت نشده است و تا زمانی که "
                "پرداخت آن تأیید نشود، فقط می‌توان آن را لغو کرد "
                "(تأیید، آماده‌سازی، ارسال و تحویل نیازمند پرداخت است)."
            )
        method_config = shipping_module.get_shipping_methods().get(order.shipping_method, {})
        quick_needs_tracking = (
            Order.Status.SHIPPED in allowed
            and method_config.get("requires_address", True)
            and not order.tracking_code
        )

        last_attempt = self.last_payment_attempt(order)
        return {
            "cusin_order_summary": True,
            "summary_items": summary_items,
            "summary_payments": order.payments.order_by("-created_at")[:5],
            "summary_last_attempt": (
                {
                    "label": LAST_ATTEMPT_PHRASES.get(
                        last_attempt.status, last_attempt.get_status_display()
                    ),
                    "raw_label": last_attempt.get_status_display(),
                    "at": last_attempt.created_at,
                    "status": last_attempt.status,
                    "reason": last_attempt.failure_reason or "",
                }
                if last_attempt is not None
                else None
            ),
            "summary_stepper_steps": steps,
            "summary_terminal": terminal,
            "quick_allowed": quick_allowed,
            "quick_blocked": quick_blocked,
            "unpaid_warning": unpaid_warning,
            "awaiting_confirmation": (
                order.payment_status == Order.PaymentStatus.PAID
                and order.status == Order.Status.PENDING
            ),
            "quick_needs_tracking": quick_needs_tracking,
            "quick_can_change": self.has_change_permission(request, order),
            "quick_status_url": reverse("admin:orders_order_quick_status", args=[order.pk]),
            "order_print_url": reverse("admin:orders_order_print", args=[order.pk]),
            "whatsapp_link": _whatsapp_link(order.shipping_phone),
            "shipping_method_label_text": shipping_module.method_label(order.shipping_method),
            "customer_order_count": order.user.orders.count(),
        }

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/print/",
                self.admin_site.admin_view(self.print_view),
                name="orders_order_print",
            ),
            # B3c: quick status transitions. Additive -- the existing
            # change form, workflow routing in save_model() and the bulk
            # actions are untouched.
            path(
                "<int:pk>/quick-status/",
                self.admin_site.admin_view(self.quick_status_view),
                name="orders_order_quick_status",
            ),
        ]
        return custom + urls

    def quick_status_view(self, request, pk):
        """Staff-only POST endpoint applying one workflow-legal transition.

        * permission: standard change permission on this order;
        * CSRF: enforced (no csrf_exempt anywhere -- the button lives in a
          real <form> with {% csrf_token %});
        * validity: only transitions in ALLOWED_TRANSITIONS from the row's
          CURRENT status are accepted; everything else is rejected with a
          message and persists nothing;
        * tracking code: when the target is «shipped» for a courier method,
          the inline field is persisted BEFORE set_status so the workflow
          precondition passes under the row lock; pickup never asks for it;
        * audit: every change is written to django LogEntry.
        """
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:orders_order_change", args=[pk]))

        order = get_object_or_404(Order, pk=pk)
        if not self.has_change_permission(request, order):
            raise PermissionDenied

        back_url = reverse("admin:orders_order_change", args=[pk])
        raw_status = request.POST.get("next_status", "")
        try:
            target = Order.Status(raw_status)
        except ValueError:
            messages.error(request, "وضعیت درخواستی معتبر نیست.")
            return HttpResponseRedirect(back_url)

        if target not in allowed_next_statuses(order.status):
            current_label = Order.Status(order.status).label
            messages.error(
                request,
                f"تغییر وضعیت از «{current_label}» به «{target.label}» طبق گردش کار سفارش مجاز نیست.",
            )
            return HttpResponseRedirect(back_url)

        payment_reason = payment_block_reason(order, target)
        if payment_reason:
            messages.error(request, payment_reason)
            return HttpResponseRedirect(back_url)

        tracking = (request.POST.get("tracking_code") or "").strip()
        if tracking:
            if target != Order.Status.SHIPPED:
                messages.error(request, "کد رهگیری فقط هنگام تغییر وضعیت به «ارسال شده» پذیرفته می‌شود.")
                return HttpResponseRedirect(back_url)
            if tracking != order.tracking_code:
                order.tracking_code = tracking
                order.save(update_fields=["tracking_code", "updated_at"])
                self.log_change(request, order, f"کد رهگیری «{tracking}» ثبت شد.")

        from . import shipping as shipping_module

        method_config = shipping_module.get_shipping_methods().get(order.shipping_method, {})
        if (
            target == Order.Status.SHIPPED
            and method_config.get("requires_address", True)
            and not order.tracking_code
        ):
            messages.error(request, "پیش از ثبت «ارسال شده»، کد رهگیری مرسوله را وارد کنید.")
            return HttpResponseRedirect(back_url)

        refund_before = order.refund_status
        try:
            set_status(order, target)
        except OrderWorkflowError as exc:
            messages.error(request, f"تغییر وضعیت انجام نشد: {exc}")
            return HttpResponseRedirect(back_url)

        order.refresh_from_db()
        self.log_change(request, order, f"تغییر سریع وضعیت به «{target.label}».")
        messages.success(request, f"وضعیت سفارش به «{target.label}» تغییر کرد.")
        if (
            refund_before != Order.RefundStatus.REQUIRED
            and order.refund_status == Order.RefundStatus.REQUIRED
        ):
            messages.warning(
                request,
                f"این سفارش نیازمند بازپرداخت وجه به مبلغ {order.refund_amount:,} تومان است — "
                "بازپرداخت را از پنل درگاه انجام دهید و سپس اینجا ثبت کنید.",
            )
        return HttpResponseRedirect(back_url)

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
                db_obj.status, requested_status, obj.tracking_code, obj.shipping_method,
                payment_status=obj.payment_status,
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

    @admin.action(
        description="خروجی اکسل سفارش‌های انتخاب‌شده",
        permissions=("view",),
    )
    def export_orders_xlsx(self, request, queryset):
        """Real .xlsx of the selected/filtered rows (Task 3).

        Row-capped so a huge filter can never time out the worker; the
        owner gets a Persian notice when the cap was hit. Dates are Jalali
        TEXT and money is a real number with a thousands format.
        """
        from apps.analytics.exports import row_limit, xlsx_bytes, xlsx_response
        from apps.adminui.jalali import format_jalali

        limit = row_limit()
        rows_qs = (
            queryset.select_related("user")
            .annotate(_items_count=Count("items"))
            .order_by("-created_at")
        )
        selected = list(rows_qs[: limit + 1])
        truncated = len(selected) > limit
        rows = []
        for order in selected[:limit]:
            customer = order.user
            name = (
                (customer.get_full_name() or "").strip()
                if customer else order.shipping_recipient_name
            ) or order.shipping_recipient_name
            rows.append([
                order.order_number,
                format_jalali(order.created_at, persian_digits=False),
                name,
                order.shipping_phone,
                order.shipping_city,
                order.get_status_display(),
                order.get_payment_status_display(),
                order._items_count,
                order.total,
                order.discount_amount,
                shipping_method_label(order.shipping_method),
            ])
        if truncated:
            self.message_user(
                request,
                f"خروجی به {limit:,} ردیف محدود شد؛ برای بقیهٔ ردیف‌ها فیلتر را محدودتر کنید.",
                messages.WARNING,
            )
        data, _written = xlsx_bytes(
            [
                "شمارهٔ سفارش", "تاریخ (شمسی)", "مشتری", "تلفن", "شهر",
                "وضعیت سفارش", "وضعیت پرداخت", "تعداد اقلام", "مبلغ نهایی (تومان)",
                "تخفیف (تومان)", "روش ارسال",
            ],
            rows,
            sheet_title="سفارش‌ها",
            numeric_columns={7, 8, 9},
        )
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        return xlsx_response(data, f"orders-{stamp}.xlsx")

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
