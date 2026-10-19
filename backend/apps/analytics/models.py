"""
Behaviour-event model (privacy-friendly analytics).

What is stored
--------------
* the event type (product_view, add_to_cart, remove_from_cart,
  wishlist_add, search, checkout_started, order_placed, order_paid);
* an optional product / order / logged-in user;
* an ANONYMOUS RANDOM session key generated in the shopper's browser
  (localStorage) -- this is what "session" means in every report;
* the search query and its result count for ``search`` events;
* province/city when they are known from the order (no address, no phone);
* a timestamp.

What is deliberately NOT stored
-------------------------------
No IP address, no user agent, no referrer, no device fingerprint. The
endpoint reads the User-Agent only to drop obvious bots, and throws it
away (see apps/analytics/tracking.py). Session keys are random UUID-like
strings, not derived from anything about the person.

Retention
---------
Raw events are pruned after ``ANALYTICS_RETENTION_DAYS`` (default 365)
by ``manage.py prune_analytics_events``, which the production scheduler
runs daily.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.products.models import Product


class Event(models.Model):
    class Type(models.TextChoices):
        PRODUCT_VIEW = "product_view", "بازدید محصول"
        ADD_TO_CART = "add_to_cart", "افزودن به سبد خرید"
        REMOVE_FROM_CART = "remove_from_cart", "حذف از سبد خرید"
        WISHLIST_ADD = "wishlist_add", "افزودن به علاقه‌مندی‌ها"
        SEARCH = "search", "جستجو"
        CHECKOUT_STARTED = "checkout_started", "شروع تسویه حساب"
        ORDER_PLACED = "order_placed", "ثبت سفارش"
        ORDER_PAID = "order_paid", "پرداخت سفارش"

    event_type = models.CharField(
        "نوع رویداد", max_length=32, choices=Type.choices,
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="analytics_events", verbose_name="محصول",
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="analytics_events", verbose_name="سفارش",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="analytics_events", verbose_name="کاربر",
    )
    # Anonymous random browser key -- never the IP, never anything derived
    # from the person. Blank only for events created without a browser
    # session (server-side order events fall back to ``u:<id>``).
    session_key = models.CharField(
        "کلید ناشناس نشست", max_length=64, blank=True, default="", db_index=True,
    )
    search_query = models.CharField("عبارت جستجو", max_length=200, blank=True, default="")
    search_results = models.PositiveIntegerField(
        "تعداد نتیجه", null=True, blank=True,
        help_text="برای رویداد جستجو؛ صفر یعنی جستجوی بی‌نتیجه.",
    )
    province = models.CharField("استان", max_length=100, blank=True, default="")
    city = models.CharField("شهر", max_length=100, blank=True, default="")

    created_at = models.DateTimeField(
        "زمان", default=timezone.now, db_index=True,
    )

    class Meta:
        verbose_name = "رویداد رفتاری"
        verbose_name_plural = "رویدادهای رفتاری"
        ordering = ["-created_at"]
        indexes = [
            # Every report window filters by type + time.
            models.Index(fields=["event_type", "created_at"], name="analytics_type_created_idx"),
            # Product-level reports (views, cart adds, wishlist adds).
            models.Index(fields=["product", "event_type"], name="analytics_product_type_idx"),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} — {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_identifiable(self) -> bool:
        """Only a logged-in user or an order makes an event attributable."""
        return bool(self.user_id or self.order_id)
