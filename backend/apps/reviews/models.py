"""
Reviews models.

Introduced in Phase 2 (Database Architecture & Models), per master spec
section 30. Moderation logic (auto-flagging, notification on approval,
etc.) is later-phase business logic -- this phase establishes the schema
and the moderation *status field* itself, plus the admin actions to move
between statuses (see admin.py), which is data management, not business
logic.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.products.models import Product


class Review(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(
        default=False,
        help_text="Whether this review is linked to a completed order for this product. "
        "Set by Phase 6 order-completion logic, not editable data entry.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Review"
        verbose_name_plural = "Reviews"
        ordering = ["-created_at"]
        constraints = [
            # One review per user per product -- edit the existing review
            # instead of creating a second one.
            models.UniqueConstraint(fields=["product", "user"], name="unique_review_per_user_product"),
        ]
        indexes = [
            models.Index(fields=["product", "status"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.product.name} ({self.rating}\u2605)"
