"""
Categories admin registration (Task 3: parent vs. sub-category clarity).

The changelist reads as a tree -- indented names («└ …» for children),
a product count that includes descendants, an active/inactive badge
and a «+ زیردسته» button per row -- so the owner never has to guess
which rows are grouping parents and which are leaf categories that
hold products.
"""
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.db.models import Case, Count, IntegerField, When
from django.urls import reverse
from django.utils.html import format_html

from apps.adminui.templatetags.adminui_extras import group_thousands, to_fa_digits

from .models import Category


def _tree_maps():
    """(children_map, depth_map, subtree_count_map) over ALL categories.

    One annotated values query for the whole (small) catalog; counts
    include every product in the subtree, active or not -- this is an
    owner inventory view, not the storefront.
    """
    rows = list(
        Category.objects.annotate(_direct=Count("products", distinct=True)).values(
            "pk", "parent_id", "ordering", "name", "_direct"
        )
    )
    children = {}
    for row in rows:
        children.setdefault(row["parent_id"], []).append(row)
    for siblings in children.values():
        siblings.sort(key=lambda r: (r["ordering"], r["name"], r["pk"]))

    depth = {}
    subtree = {}
    # Iterative DFS (pre-order for depth, post-order accumulation).
    stack = [(row, 0, False) for row in reversed(children.get(None, []))]
    seen = set()
    while stack:
        row, level, expanded = stack.pop()
        if expanded:
            total = row["_direct"]
            for child in children.get(row["pk"], []):
                total += subtree.get(child["pk"], child["_direct"])
            subtree[row["pk"]] = total
            continue
        if row["pk"] in seen:  # corrupt cycle guard
            continue
        seen.add(row["pk"])
        depth[row["pk"]] = level
        stack.append((row, level, True))
        for child in reversed(children.get(row["pk"], [])):
            stack.append((child, level + 1, False))
    # Rows orphaned by a corrupt cycle still get sane fallbacks.
    for row in rows:
        depth.setdefault(row["pk"], 0)
        subtree.setdefault(row["pk"], row["_direct"])
    return children, depth, subtree


def _dfs_order(children):
    """Category pks in depth-first tree order (parents before children)."""
    order = []
    stack = list(reversed(children.get(None, [])))
    seen = set()
    while stack:
        row = stack.pop()
        if row["pk"] in seen:
            continue
        seen.add(row["pk"])
        order.append(row["pk"])
        for child in reversed(children.get(row["pk"], [])):
            stack.append(child)
    return order


class CategoryChangeList(ChangeList):
    """Tree-ordered changelist (unless the owner sorts a column)."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.params.get("o"):
            return qs
        children, _depth, _subtree = _tree_maps()
        wanted = set(qs.values_list("pk", flat=True))
        ordered = [pk for pk in _dfs_order(children) if pk in wanted]
        # Filtered rows whose ancestors are filtered out (or corrupt
        # leftovers) keep their relative place at the end.
        ordered += [pk for pk in wanted if pk not in set(ordered)]
        if not ordered:
            return qs
        whens = [When(pk=pk, then=pos) for pos, pk in enumerate(ordered)]
        return qs.order_by(Case(*whens, output_field=IntegerField()))

    def get_results(self, request):
        super().get_results(request)
        _children, depth, subtree = _tree_maps()
        for obj in self.result_list:
            obj._tree_depth = depth.get(obj.pk, 0)
            obj._subtree_product_count = subtree.get(obj.pk, 0)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "tree_name", "subtree_product_count", "active_badge",
        "ordering", "add_subcategory",
    )
    list_display_links = ("tree_name",)
    list_editable = ("ordering",)
    list_filter = ("is_active", "is_catalog_root", "parent")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("parent",)
    ordering = ("ordering", "name")

    def get_changelist(self, request, **kwargs):
        return CategoryChangeList

    def get_queryset(self, request):
        # Remembered for the «+ زیردسته» column (display methods get
        # no request of their own).
        self._request_has_add = self.has_add_permission(request)
        return (
            super()
            .get_queryset(request)
            .select_related("parent", "parent__parent", "parent__parent__parent")
        )

    def get_changeform_initial_data(self, request):
        """«+ زیردسته» opens ``add/?parent=<pk>`` with the parent set."""
        initial = super().get_changeform_initial_data(request)
        parent = request.GET.get("parent")
        if parent:
            try:
                initial["parent"] = Category.objects.get(pk=parent)
            except (Category.DoesNotExist, ValueError, TypeError):
                pass
        return initial

    @admin.display(description="دسته‌بندی", ordering="name")
    def tree_name(self, obj):
        depth = getattr(obj, "_tree_depth", obj.depth)
        indent_px = depth * 22
        prefix = "└ " if depth else ""
        root_badge = (
            ' <span class="cusin-badge on">ریشهٔ کاتالوگ</span>'
            if obj.is_catalog_root else ""
        )
        return format_html(
            '<span class="cusin-tree-name" style="padding-inline-start:{}px" title="{}">{}<span>{}</span>{}</span>',
            indent_px,
            obj.full_path,
            prefix,
            obj.name,
            format_html(root_badge) if root_badge else "",
        )

    @admin.display(description="تعداد محصولات")
    def subtree_product_count(self, obj):
        count = getattr(obj, "_subtree_product_count", None)
        if count is None:
            count = obj.products.count()
        return to_fa_digits(group_thousands(count))

    @admin.display(description="وضعیت", ordering="is_active", boolean=False)
    def active_badge(self, obj):
        if obj.is_active:
            return format_html('<span class="cusin-badge on">فعال</span>')
        return format_html('<span class="cusin-badge off">غیرفعال</span>')

    @admin.display(description="")
    def add_subcategory(self, obj):
        if not getattr(self, "_request_has_add", False):
            return ""
        url = f"{reverse('admin:categories_category_add')}?parent={obj.pk}"
        return format_html(
            '<a class="cusin-btn cusin-btn--ghost cusin-btn--sm" href="{}" '
            'data-cusin-modal data-cusin-modal-reload="1" '
            'title="ساخت زیردسته برای «{}»">+ زیردسته</a>',
            url,
            obj.name,
        )

    def changelist_view(self, request, extra_context=None):
        """Warn, in place, about products sitting on a parent category."""
        extra_context = dict(extra_context or {})
        from apps.products.models import Product

        misplaced = list(
            Product.objects.filter(category__children__isnull=False)
            .select_related("category")
            .distinct()
            .order_by("category__ordering", "category__name", "name")[:100]
        )
        extra_context["products_on_parents"] = [
            {
                "product": product,
                "change_url": reverse(
                    "admin:products_product_change", args=[product.pk]
                ),
            }
            for product in misplaced
        ]
        extra_context["products_on_parents_count"] = (
            Product.objects.filter(category__children__isnull=False)
            .distinct()
            .count()
        )
        extra_context["products_changelist_url"] = reverse(
            "admin:products_product_changelist"
        )
        return super().changelist_view(request, extra_context=extra_context)
