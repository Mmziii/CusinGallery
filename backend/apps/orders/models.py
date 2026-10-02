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
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        RETURNED = "returned", "Returned"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    order_number = models.CharField(max_length=32, unique=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )

    subtotal = models.PositiveBigIntegerField()
    discount_amount = models.PositiveBigIntegerField(default=0)
    shipping_cost = models.PositiveBigIntegerField(default=0)
    total = models.PositiveBigIntegerField()

    coupon = models.ForeignKey(
        "discounts.Coupon",
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
    )

    # --- Shipping address snapshot ---------------------------------------
    # Deliberately flat fields, NOT a FK to accounts.Address. Per master
    # spec section 23, an order must remain historically correct even if
    # the customer later edits or deletes that saved address.
    shipping_recipient_name = models.CharField(max_length=150)
    shipping_phone = models.CharField(max_length=20)
    shipping_province = models.CharField(max_length=100)
    shipping_city = models.CharField(max_length=100)
    shipping_address = models.TextField()
    shipping_postal_code = models.CharField(max_length=20)
    shipping_unit = models.CharField(max_length=20, blank=True)
    shipping_building_number = models.CharField(max_length=20, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "payment_status"]),
            models.Index(fields=["created_at"]),
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
        Product, on_delete=models.SET_NULL, related_name="order_items", null=True
    )
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, related_name="order_items", null=True, blank=True
    )

    # --- Snapshot fields, per master spec section 23 -----------------------
    product_name = models.CharField(max_length=255)
    sku = models.CharField("SKU", max_length=64)
    unit_price = models.PositiveBigIntegerField()
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    total_price = models.PositiveBigIntegerField()

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
        indexes = [
            models.Index(fields=["order"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"
