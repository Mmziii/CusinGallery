"""
Categories models.

Introduced in Phase 2 (Database Architecture & Models), per master spec
section 11. Hierarchical category tree using a simple adjacency-list
design (self-referencing FK) rather than a nested-set/MPTT library --
this keeps Phase 2 dependency-free while still fully supporting the
parent/child queries later phases need (shop filtering, breadcrumbs,
homepage sections). If catalog depth ever makes recursive queries a
performance problem, django-mptt (or Postgres recursive CTEs) can be
layered on top of this same `parent` field without a schema rewrite.
"""
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import ActivableModel, OrderableModel, TimeStampedModel


class Category(TimeStampedModel, ActivableModel, OrderableModel):
    """A product category, optionally nested under a parent category."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
        help_text="Leave empty for a top-level category.",
    )
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ["ordering", "name"]
        indexes = [
            models.Index(fields=["parent", "is_active"]),
            models.Index(fields=["is_active", "ordering"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        """
        Prevents a category from becoming its own ancestor. Runs on every
        admin save (ModelForm calls full_clean()) so a cyclical tree can
        never be created through the admin, even indirectly across
        several edits.
        """
        if not self.parent_id:
            return
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "A category cannot be its own parent."})

        ancestor = self.parent
        seen_ids = set()
        while ancestor is not None:
            if self.pk and ancestor.pk == self.pk:
                raise ValidationError(
                    {"parent": "This would create a circular category hierarchy."}
                )
            if ancestor.pk in seen_ids:
                # Pre-existing corrupt data upstream of this node -- don't
                # loop forever; this save is still safe since it's not
                # part of that cycle.
                break
            seen_ids.add(ancestor.pk)
            ancestor = ancestor.parent
