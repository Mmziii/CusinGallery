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

from apps.core.image_files import validate_image_file
from apps.core.models import ActivableModel, OrderableModel, TimeStampedModel


class Category(TimeStampedModel, ActivableModel, OrderableModel):
    """A product category, optionally nested under a parent category.

    The single catalog root («آشپزخانه») is marked with
    ``is_catalog_root`` -- never identified by name/slug in runtime
    code -- so renaming it (name or slug) cannot break the storefront
    grouping, which shows the root's children as the main groups.
    """

    name = models.CharField("نام دسته‌بندی", max_length=150)
    slug = models.SlugField("شناسه (آدرس)", max_length=170, unique=True, allow_unicode=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
        verbose_name="دستهٔ والد",
        help_text=(
            "دستهٔ والد یعنی این دسته زیرمجموعهٔ آن قرار می‌گیرد؛ مثلاً «قابلمه» زیرِ "
            "«پخت‌وپز». برای یک گروهِ اصلی در بالاترین سطح، این کادر را خالی بگذارید. "
            "محصول فقط در زیردسته‌ها قرار می‌گیرد (دسته‌هایی که خودشان زیردسته ندارند)؛ "
            "دسته‌های والد فقط گروه‌بندی هستند و محصول مستقیم نمی‌گیرند."
        ),
    )
    is_catalog_root = models.BooleanField(
        "ریشهٔ کاتالوگ",
        default=False,
        help_text=(
            "فقط یک دسته می‌تواند ریشهٔ کاتالوگ باشد (همان «آشپزخانه»). فروشگاه، "
            "گروه‌های اصلی را از زیردسته‌های همین ریشه نشان می‌دهد؛ برای بقیهٔ "
            "دسته‌ها این تیک را نزنید."
        ),
    )
    image = models.ImageField(
        "تصویر", upload_to="categories/", blank=True, null=True, validators=[validate_image_file]
    )
    description = models.TextField("توضیحات", blank=True)

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["ordering", "name"]
        indexes = [
            models.Index(fields=["parent", "is_active"]),
            models.Index(fields=["is_active", "ordering"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["is_catalog_root"],
                condition=models.Q(is_catalog_root=True),
                name="only_one_catalog_root",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Part R5 item 7: a category rename must propagate into the
        # normalized search index of its products (the index embeds the
        # category name).
        old_name = None
        if self.pk:
            old_name = (
                type(self).objects.filter(pk=self.pk).values_list("name", flat=True).first()
            )
        super().save(*args, **kwargs)
        if old_name is not None and old_name != self.name:
            from apps.products.search import refresh_search_fields

            refresh_search_fields(self.products.all())

    @classmethod
    def catalog_root(cls):
        """The single catalog root category, or None when unset."""
        return cls.objects.filter(is_catalog_root=True).first()

    def ancestor_chain(self):
        """Ancestors top-most first, EXCLUDING self (cycle-guarded)."""
        chain = []
        seen = set()
        node = self.parent
        while node is not None and node.pk not in seen:
            seen.add(node.pk)
            chain.append(node)
            node = node.parent
            if len(chain) >= 10:
                break
        chain.reverse()
        return chain

    @property
    def full_path(self):
        """«آشپزخانه › پخت‌وپز › قابلمه» -- root-first, including self."""
        names = [ancestor.name for ancestor in self.ancestor_chain()]
        names.append(self.name)
        return " › ".join(names)

    @property
    def depth(self):
        return len(self.ancestor_chain())

    @property
    def is_leaf(self):
        """True when this category has no sub-categories (products go here)."""
        return not self.children.exists()

    def clean(self):
        """
        Prevents a category from becoming its own ancestor. Runs on every
        admin save (ModelForm calls full_clean()) so a cyclical tree can
        never be created through the admin, even indirectly across
        several edits.
        """
        if self.is_catalog_root and self.parent_id:
            raise ValidationError(
                {"is_catalog_root": "ریشهٔ کاتالوگ نمی‌تواند خودش دستهٔ والد داشته باشد."}
            )
        if self.is_catalog_root:
            others = type(self).objects.filter(is_catalog_root=True)
            if self.pk:
                others = others.exclude(pk=self.pk)
            if others.exists():
                raise ValidationError(
                    {"is_catalog_root": "فقط یک دسته می‌تواند ریشهٔ کاتالوگ باشد؛ اول تیکِ ریشه را از آن دسته بردارید."}
                )
        if not self.parent_id:
            return
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "دسته‌بندی نمی‌تواند والدِ خودش باشد."})

        ancestor = self.parent
        seen_ids = set()
        while ancestor is not None:
            if self.pk and ancestor.pk == self.pk:
                raise ValidationError(
                    {"parent": "این تغییر باعث ایجاد چرخه در سلسله‌مراتب دسته‌بندی‌ها می‌شود."}
                )
            if ancestor.pk in seen_ids:
                # Pre-existing corrupt data upstream of this node -- don't
                # loop forever; this save is still safe since it's not
                # part of that cycle.
                break
            seen_ids.add(ancestor.pk)
            ancestor = ancestor.parent
