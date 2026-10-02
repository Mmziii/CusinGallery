"""
Categories views.

Entirely read-only: there is no create/update/delete endpoint here at
all (ReadOnlyModelViewSet), by design -- see master spec section 16.
Catalog data is only ever modified through Django Admin (/admin/, staff
only, unaffected by anything here), so there's no separate write-API
surface to secure in the first place.
"""
from django.db.models import Count, Prefetch, Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Category
from .serializers import CategorySerializer, CategoryTreeSerializer

# How many levels deep GET /categories/tree/ eagerly loads via nested
# Prefetch. Django's ORM has no native "prefetch arbitrarily deep"
# primitive for a self-referencing adjacency-list tree (see
# Category's own model docstring on this exact tradeoff) -- this bound
# keeps the endpoint at a small, fixed number of queries (one per level)
# instead of an open-ended N+1 for pathologically deep trees. Comfortably
# covers realistic catalog depth (e.g. Cookware > Pots > Non-stick); a
# 5th-level-and-deeper child would still be excluded from this endpoint,
# not silently broken -- a store needing deeper nesting should reconsider
# the category structure or revisit this bound.
TREE_PREFETCH_DEPTH = 4


def _build_children_prefetch(depth):
    active_children = Category.objects.filter(is_active=True).annotate(
        product_count=Count("products", filter=Q(products__is_active=True), distinct=True)
    ).order_by("ordering", "name")
    if depth > 1:
        active_children = active_children.prefetch_related(
            Prefetch("children", queryset=_build_children_prefetch(depth - 1))
        )
    return active_children


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        # Inactive categories are excluded entirely from the public API,
        # not merely hidden from anonymous users -- there is no
        # "logged-in customers can see inactive categories" case, per
        # master spec section 20. Managing inactive categories stays a
        # Django Admin concern.
        return (
            Category.objects.filter(is_active=True)
            .select_related("parent")
            .annotate(
                product_count=Count(
                    "products", filter=Q(products__is_active=True), distinct=True
                )
            )
        )

    @action(detail=False, methods=["get"])
    def tree(self, request):
        roots = (
            Category.objects.filter(is_active=True, parent__isnull=True)
            .annotate(
                product_count=Count(
                    "products", filter=Q(products__is_active=True), distinct=True
                )
            )
            .order_by("ordering", "name")
            .prefetch_related(
                Prefetch("children", queryset=_build_children_prefetch(TREE_PREFETCH_DEPTH))
            )
        )
        # tree_depth/tree_max_depth make the serializer's recursion stop
        # exactly where the prefetch chain above stops -- see
        # CategoryTreeSerializer.get_children for why continuing past the
        # prefetched levels would reintroduce the N+1 this is built to
        # prevent (and why the docstring above says deeper children are
        # excluded from this endpoint).
        serializer = CategoryTreeSerializer(
            roots,
            many=True,
            context={"request": request, "tree_depth": 0, "tree_max_depth": TREE_PREFETCH_DEPTH},
        )
        return Response(serializer.data)
