"""
Products views.

Entirely read-only, same reasoning as apps/categories/views.py: no
create/update/delete endpoint exists here at all -- catalog data is only
ever modified through Django Admin (staff-only, unaffected by anything
here).
"""
from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
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
        queryset = Brand.objects.filter(is_active=True)
        # Part R2: /brands/?is_featured=true powers the home page brand
        # tiles, ordered by display_order then name.
        is_featured = self.request.query_params.get("is_featured")
        if is_featured in ("true", "1"):
            queryset = queryset.filter(is_featured=True).order_by("display_order", "name")
        return queryset


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


class BackInStockView(APIView):
    """POST /products/back-in-stock/ (Part 2): public, throttled.
    Accepts {product_id, variant_id?, phone(09xxxxxxxxx)} for an
    OUT-OF-STOCK item; duplicate active subscriptions answer 200 with a
    generic "already registered" note (no enumeration of anything
    sensitive here, but no need to double-create either)."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "back_in_stock"

    def post(self, request):
        from rest_framework import exceptions as drf_exceptions

        from .models import BackInStockSubscription, Product, ProductVariant, iranian_mobile_validator

        try:
            product_id = int(request.data.get("product_id"))
        except (TypeError, ValueError):
            raise drf_exceptions.ValidationError({"product_id": ["product_id is required."]})
        variant_id = request.data.get("variant_id")
        phone = (request.data.get("phone") or "").strip()

        try:
            iranian_mobile_validator(phone)
        except DjangoValidationError as exc:
            raise drf_exceptions.ValidationError({"phone": exc.messages})

        try:
            product = Product.objects.get(pk=product_id, is_active=True)
        except Product.DoesNotExist:
            raise drf_exceptions.ValidationError({"product_id": ["محصول پیدا نشد."]})

        variant = None
        if variant_id not in (None, ""):
            try:
                variant = ProductVariant.objects.get(pk=int(variant_id), product=product, is_active=True)
            except (ProductVariant.DoesNotExist, TypeError, ValueError):
                raise drf_exceptions.ValidationError({"variant_id": ["این تنوع متعلق به این محصول نیست."]})

        in_stock = (variant.stock_quantity if variant else product.stock_quantity) > 0
        if in_stock:
            return Response(
                {"detail": "این کالا هم‌اکنون موجود است و نیازی به اطلاع‌رسانی نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _sub, created = BackInStockSubscription.objects.get_or_create(
            phone=phone, product=product, variant=variant,
            defaults={"notified_at": None},
        )
        return Response(
            {"detail": "ثبت شد؛ به محض موجودشدن، پیامک اطلاع‌رسانی دریافت می‌کنید."},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
