"""
Products views.

Entirely read-only, same reasoning as apps/categories/views.py: no
create/update/delete endpoint exists here at all -- catalog data is only
ever modified through Django Admin (staff-only, unaffected by anything
here).
"""
from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter

from .filters import ProductFilter
from .models import Brand, Product, ProductImage
from .serializers import BrandSerializer, ProductDetailSerializer, ProductListSerializer

# Maps a friendly, stable `?ordering=` value to the real field ordering.
# Deliberately NOT exposing raw model field names as the API's sort
# contract (e.g. "-price") -- that would leak internal field names into
# the frontend/API contract and break silently if a field were ever
# renamed. "popularity" is intentionally absent: no such data exists yet
# (would need real order/sales history from a phase not yet built), per
# master spec section 4's "do not invent popularity metrics that don't
# exist."
ORDERING_OPTIONS = {
    "newest": "-created_at",
    "oldest": "created_at",
    "price_asc": "price",
    "price_desc": "-price",
}
DEFAULT_ORDERING = "newest"


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BrandSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        # Same reasoning as CategoryViewSet: inactive brands are excluded
        # entirely from the public API, not merely hidden from anon users.
        return Brand.objects.filter(is_active=True)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "sku", "short_description", "brand__name", "category__name"]

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == "retrieve" else ProductListSerializer

    def get_queryset(self):
        # select_related for FKs shown on every row (category, brand);
        # prefetch_related for the primary-image lookup in
        # ProductListSerializer.get_primary_image, ordered so the primary
        # image (if any) is first -- both exist specifically to avoid a
        # per-product query, i.e. N+1, across a paginated list of up to
        # PAGE_SIZE (20, see settings) products.
        queryset = (
            Product.objects.filter(is_active=True)
            .select_related("category", "brand")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_primary", "ordering"),
                )
            )
        )
        return queryset.order_by(self._resolve_ordering())

    def _resolve_ordering(self):
        raw = self.request.query_params.get("ordering", DEFAULT_ORDERING)
        if raw not in ORDERING_OPTIONS:
            raise ValidationError(
                {
                    "ordering": (
                        f"'{raw}' is not a supported ordering. "
                        f"Choose one of: {', '.join(ORDERING_OPTIONS)}."
                    )
                }
            )
        return ORDERING_OPTIONS[raw]
