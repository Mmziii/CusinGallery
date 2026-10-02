"""
Categories serializers.
"""
from rest_framework import serializers

from .models import Category


class CategorySerializer(serializers.ModelSerializer):
    """Used for the flat list/detail endpoints."""

    product_count = serializers.IntegerField(read_only=True)
    # In addition to the raw `parent` id (kept for completeness/any
    # future FK-based lookup), `parent_slug` is exposed because the rest
    # of this API is slug-based (category/brand/product detail lookups
    # all use slug, not id) -- per master spec section 20 ("avoid
    # database IDs unnecessarily where slugs are appropriate"), a
    # frontend building breadcrumbs/menus from this response shouldn't
    # need a second request just to resolve a parent id into a slug.
    #
    # Deliberately a SerializerMethodField, not
    # SlugField(source="parent.slug"): most categories are top-level
    # (parent=None -- see Category.parent's own null=True), and DRF's
    # dotted-source attribute traversal only catches
    # django.core.exceptions.ObjectDoesNotExist, not the plain
    # AttributeError that getattr(None, "slug") raises. That combination
    # would 500 on every top-level category -- exactly the common case,
    # not an edge case -- so this is handled explicitly instead.
    parent_slug = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id", "name", "slug", "image", "description",
            "parent", "parent_slug", "ordering", "product_count",
        ]

    def get_parent_slug(self, obj):
        return obj.parent.slug if obj.parent_id else None


class CategoryTreeSerializer(serializers.ModelSerializer):
    """
    Recursive representation for GET /categories/tree/ -- built for
    frontend navigation menus. `children` is populated from a
    prefetch_related("children") queryset already filtered to active
    categories at the view level (see CategoryViewSet.tree), so this
    serializer itself issues no additional queries per node -- for every
    level the view actually prefetched, that is. Recursion deliberately
    STOPS at that same depth ("tree_depth" in the serializer context,
    seeded by CategoryViewSet.tree): beyond it nothing is prefetched, so
    continuing would fall back to one lazy query per node -- exactly the
    N+1 the prefetch chain exists to avoid. This is what the view's
    docstring means by deeper children being excluded from the endpoint.
    """

    children = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "image", "ordering", "product_count", "children"]

    def get_children(self, obj):
        depth = self.context.get("tree_depth", 0)
        max_depth = self.context.get("tree_max_depth")
        if max_depth is not None and depth >= max_depth:
            return []
        # `.all()` here hits the prefetch cache, not the database, as
        # long as the queryset was built with prefetch_related("children")
        # -- see CategoryViewSet.tree for where that's set up.
        children = obj.children.all()
        child_context = dict(self.context, tree_depth=depth + 1)
        return CategoryTreeSerializer(children, many=True, context=child_context).data
