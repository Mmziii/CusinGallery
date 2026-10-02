"""
Cart models.

Introduced in Phase 2 (Database Architecture & Models), per master spec
section 19. This is the server-side, authoritative cart for authenticated
users. Guest carts stay entirely client-side (browser storage) until
login, per the master spec -- there is deliberately no guest/session Cart
row here; that synchronization behaviour is Phase 5 business logic, not a
schema concern.

Cart pricing (subtotal/discount/shipping/total) is intentionally NOT
stored on these models -- per master spec section 19, "the backend must
calculate totals" on demand from current product prices, never trust a
stored/stale total. Computing and exposing that is a Phase 5 service-layer
concern built on top of this schema.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.products.models import Product, ProductVariant


class Cart(TimeStampedModel):
    """One cart per authenticated user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )

    class Meta:
        verbose_name = "سبد خرید"
        verbose_name_plural = "سبدهای خرید"

    def __str__(self):
        return f"Cart({self.user})"


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="cart_items",
        null=True,
        blank=True,
        help_text="Leave empty if the product has no variants.",
    )
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "قلم سبد خرید"
        verbose_name_plural = "اقلام سبد خرید"
        constraints = [
            # A plain UniqueConstraint(fields=["cart", "product", "variant"])
            # would NOT actually enforce "one row per product in this cart"
            # for products with no variant: Postgres (like SQL generally)
            # treats every NULL as distinct from every other NULL for
            # uniqueness purposes, so a single unique constraint including
            # a nullable column silently allows unlimited duplicate rows
            # wherever that column is NULL. Split into two conditional
            # (partial) constraints instead, one per case:
            models.UniqueConstraint(
                fields=["cart", "product"],
                condition=models.Q(variant__isnull=True),
                name="unique_cart_product_no_variant",
            ),
            models.UniqueConstraint(
                fields=["cart", "product", "variant"],
                condition=models.Q(variant__isnull=False),
                name="unique_cart_product_variant",
            ),
        ]
        indexes = [
            models.Index(fields=["cart"]),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    def clean(self):
        if self.variant_id and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "This variant does not belong to the selected product."})
