"""
Shared abstract base models.

These contain no business logic of their own -- they exist so every app
added from Phase 2 onward (products, orders, categories, ...) can inherit
common, consistently-named fields instead of redefining them, and so that
"is this timestamped / orderable / active" behaves identically everywhere
in the codebase.

Abstract models generate no database table and no migration by themselves;
migrations appear once a concrete model in another app inherits from one
of these.
"""
from django.db import models


class TimeStampedModel(models.Model):
    """Adds created_at / updated_at, auto-managed on save."""

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("تاریخ ویرایش", auto_now=True)

    class Meta:
        abstract = True


class ActivableModel(models.Model):
    """Adds an is_active flag, for soft enable/disable instead of deletion."""

    is_active = models.BooleanField(
        "فعال", default=True, help_text="به‌جای حذف، برای غیرفعال‌کردن موقت استفاده می‌شود."
    )

    class Meta:
        abstract = True


class OrderableModel(models.Model):
    """Adds an integer ordering field for admin-controlled display order."""

    ordering = models.PositiveIntegerField(
        "ترتیب نمایش", default=0, help_text="عدد کوچک‌تر زودتر نمایش داده می‌شود."
    )

    class Meta:
        abstract = True
        ordering = ["ordering"]
