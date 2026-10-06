"""
Orders models.

Introduced in Phase 2 (Database Architecture & Models), per master spec
sections 23-24. Checkout orchestration (converting a cart into an order,
triggering payment, decrementing stock) is explicitly Phase 6/7 business
logic -- this phase only establishes the schema, the order-number
generation needed for the model to be usable/testable in isolation (e.g.
via admin or seed data), and the snapshot-field discipline the master
spec requires: "If a product price changes later, old orders must remain
historically correct."

Coupon is referenced via Django's lazy "app_label.ModelName" string
reference (not a direct import) to avoid a circular Python import with
apps.discounts.models, which itself references Order back (CouponUsage).
See apps/discounts/models.py for the full explanation and how the
migrations are sequenced to avoid a circular *migration* dependency too.
"""
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.products.models import Product, ProductVariant


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار تأیید"
        CONFIRMED = "confirmed", "تأیید شده"
        PROCESSING = "processing", "در حال پردازش"
        SHIPPED = "shipped", "ارسال شده"
        DELIVERED = "delivered", "تحویل شده"
        CANCELLED = "cancelled", "لغو شده"
        RETURNED = "returned", "مرجوع شده"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "پرداخت نشده"
        PENDING = "pending", "در انتظار پرداخت"
        PAID = "paid", "پرداخت شده"
        FAILED = "failed", "پرداخت ناموفق"
        REFUNDED = "refunded", "مسترد شده"

    class RefundStatus(models.TextChoices):
        """Manual-refund bookkeeping (Phase C). NONE = no money owed back;
        REQUIRED = the shop is holding the customer's money and must pay
        it back through the PSP panel; REFUNDED = the owner did so and
        recorded the note/reference."""

        NONE = "none", "بدون بازپرداخت"
        REQUIRED = "required", "نیازمند بازپرداخت"
        REFUNDED = "refunded", "بازپرداخت شده"

    order_number = models.CharField("شمارهٔ سفارش", max_length=32, unique=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders",
        verbose_name="مشتری",
    )

    status = models.CharField(
        "وضعیت سفارش", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    payment_status = models.CharField(
        "وضعیت پرداخت", max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )

    subtotal = models.PositiveBigIntegerField("جمع اقلام (تومان)")
    discount_amount = models.PositiveBigIntegerField("مبلغ تخفیف (تومان)", default=0)
    shipping_cost = models.PositiveBigIntegerField("هزینهٔ ارسال (تومان)", default=0)
    total = models.PositiveBigIntegerField("مبلغ نهایی (تومان)")

    # Gift wrapping snapshot (Part 2): the fee is part of `total` (the
    # payment cross-check therefore covers it), and like every other
    # monetary field it is snapshotted at checkout -- changing
    # GIFT_WRAP_FEE later never rewrites existing orders.
    gift_wrap = models.BooleanField("بسته‌بندی هدیه", default=False)
    gift_message = models.TextField(
        "پیام هدیه", blank=True, default="",
        help_text="حداکثر ۲۰۰ کاراکتر؛ متن ساده -- در همهٔ نمایش‌ها escape می‌شود.",
    )
    gift_wrap_fee = models.PositiveBigIntegerField("هزینهٔ بسته‌بندی هدیه (تومان)", default=0)

    coupon = models.ForeignKey(
        "discounts.Coupon",
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
        verbose_name="کوپن تخفیف",
    )

    # --- Shipping address snapshot ---------------------------------------
    # Deliberately flat fields, NOT a FK to accounts.Address. Per master
    # spec section 23, an order must remain historically correct even if
    # the customer later edits or deletes that saved address.
    shipping_recipient_name = models.CharField("نام گیرنده", max_length=150)
    shipping_phone = models.CharField("تلفن گیرنده", max_length=20)
    shipping_province = models.CharField("استان", max_length=100)
    shipping_city = models.CharField("شهر", max_length=100)
    shipping_address = models.TextField("آدرس کامل")
    shipping_postal_code = models.CharField("کد پستی", max_length=20)
    shipping_unit = models.CharField("واحد", max_length=20, blank=True)
    shipping_building_number = models.CharField("پلاک", max_length=20, blank=True)

    # --- Shipping method + delivery-window snapshot -----------------------
    # Written ONCE at checkout from the settings that were in force at
    # that moment (apps.orders.services.checkout -> apps.orders.shipping).
    # Like the address snapshot above, these are historical facts about
    # the order, never re-derived from settings afterwards: if the shop
    # later changes shipping costs or delivery windows, existing orders
    # keep exactly what the customer was promised and charged.
    shipping_method = models.CharField("روش ارسال", max_length=20, default="standard")
    estimated_delivery_min = models.DateField("زودترین تاریخ تحویل", null=True, blank=True)
    estimated_delivery_max = models.DateField("دیرترین تاریخ تحویل", null=True, blank=True)

    # --- Fulfilment workflow (Phase B - Store management) -------------------
    # Carrier tracking code, entered by the shop owner when the order is
    # marked shipped (see apps/orders/workflow.py).
    tracking_code = models.CharField(
        "کد رهگیری پستی", max_length=100, blank=True,
        help_text="پیش از تغییر وضعیت به «ارسال شده» وارد کنید.",
    )
    # Set exactly once when a cancelled PAID order's stock is handed back
    # (workflow.set_status -> inventory.restore_stock_for_order). The
    # timestamp is the idempotency guard: a second cancel attempt can
    # never restore stock again.
    stock_restored_at = models.DateTimeField("زمان بازگشت موجودی", null=True, blank=True)

    # --- Refund tracking (Phase C - Real payments) ---------------------------
    # There is NO automatic refund integration: Iranian PSP refunds are
    # executed manually by the owner in the PSP's merchant panel. What the
    # system guarantees instead is that real money the shop owes back to a
    # customer is NEVER lost from view: whenever a PAID order is cancelled
    # or returned (apps/orders/workflow.py), or a gateway-verified capture
    # cannot be applied to an order (late success after auto-cancellation,
    # a duplicate second capture -- apps/payments/services.py), the order
    # is flagged "refund required" with an amount and an append-only note
    # journal, and stays in the admin's refund filter until the owner marks
    # it refunded WITH a note. All writes to these fields go through
    # apps/orders/refunds.py -- the single mechanism, same discipline as
    # inventory.py for stock.
    refund_status = models.CharField(
        "وضعیت بازپرداخت وجه", max_length=10,
        choices=RefundStatus.choices, default=RefundStatus.NONE,
    )
    refund_amount = models.PositiveBigIntegerField(
        "مبلغ بازپرداخت (تومان)", default=0,
        help_text="مجموع مبالغی که باید به مشتری بازگردانده شود (تومان).",
    )
    refund_reference = models.TextField(
        "یادداشت بازپرداخت", blank=True, default="",
        help_text="شرح رویدادهای بازپرداخت (به‌صورت تجمعی) و در نهایت مرجع/یادداشت "
        "بازپرداخت دستی در پنل درگاه. بدون افزودن یادداشت نمی‌توان سفارش را "
        "«بازپرداخت شده» کرد.",
    )
    refunded_at = models.DateTimeField("زمان بازپرداخت", null=True, blank=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("تاریخ ویرایش", auto_now=True)

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "payment_status"]),
            models.Index(fields=["created_at"]),
            # The owner's daily "which orders still owe a refund?" admin
            # filter (list_filter + the expire/refund workflows) reads
            # this column across the whole orders table.
            models.Index(fields=["refund_status"]),
        ]

    def __str__(self):
        return self.order_number or f"Order #{self.pk}"

    @staticmethod
    def generate_order_number():
        """
        Produces a unique, human-showable order number
        (e.g. "CG-20260810-9F3A21B7"). This exists purely so the Order
        model is self-consistent and usable on its own (admin-created
        orders, seed data, Phase 2 testing) -- full checkout orchestration
        (cart -> order conversion, stock decrement, payment kickoff) is
        Phase 6/7 work built on top of this.
        """
        return f"CG-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")

    # SET_NULL (not CASCADE/PROTECT): a product or variant may be removed
    # from the catalog later without invalidating historical orders -- the
    # snapshot fields below are what the order actually displays.
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, related_name="order_items", null=True,
        verbose_name="محصول",
    )
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, related_name="order_items", null=True, blank=True,
        verbose_name="تنوع",
    )

    # --- Snapshot fields, per master spec section 23 -----------------------
    product_name = models.CharField("نام کالا", max_length=255)
    sku = models.CharField("کد کالا (SKU)", max_length=64)
    unit_price = models.PositiveBigIntegerField("قیمت واحد (تومان)")
    quantity = models.PositiveIntegerField("تعداد", validators=[MinValueValidator(1)])
    total_price = models.PositiveBigIntegerField("جمع ردیف (تومان)")

    class Meta:
        verbose_name = "قلم سفارش"
        verbose_name_plural = "اقلام سفارش"
        indexes = [
            models.Index(fields=["order"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"
