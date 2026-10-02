"""
Wishlist models.

Introduced in Phase 2 (Database Architecture & Models), per master spec
section 20. Modeled as a single WishlistItem row per (user, product)
rather than a wrapping "Wishlist" container model -- a user's wishlist is
simply the set of their WishlistItem rows, which is simpler and avoids an
unused always-one-per-user table.
"""
from django.conf import settings
from django.db import models

from apps.products.models import Product


class WishlistItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Wishlist Item"
        verbose_name_plural = "Wishlist Items"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_user_product"),
        ]
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user} \u2661 {self.product.name}"
