"""
Wishlist views. Same session + CSRF authentication as everywhere else in
this project -- no second auth mechanism.
"""
from django.db.models import Prefetch
from rest_framework import permissions, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.models import Product, ProductImage

from .models import WishlistItem
from .serializers import AddWishlistItemSerializer, WishlistCheckSerializer, WishlistItemSerializer


def _wishlist_queryset(user):
    # Mirrors ProductViewSet.get_queryset's prefetch shape (Phase 4) so
    # WishlistItemSerializer's nested ProductListSerializer doesn't
    # trigger a query per item for category/brand/primary-image.
    return (
        WishlistItem.objects.filter(user=user)
        .select_related("product", "product__category", "product__brand")
        .prefetch_related(
            Prefetch("product__images", queryset=ProductImage.objects.order_by("-is_primary", "ordering"))
        )
    )


class WishlistListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = _wishlist_queryset(request.user)
        return Response(WishlistItemSerializer(items, many=True, context={"request": request}).data)


class WishlistItemCreateView(APIView):
    """
    POST /wishlist/items/ -- adds a product, or gracefully returns the
    existing entry if it's already wishlisted (never a duplicate-key
    error) -- see master spec step 13: "handle duplicate requests
    gracefully", matching the real unique_wishlist_user_product
    constraint from Phase 2.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AddWishlistItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data["product_id"]

        product = get_object_or_404(Product, pk=product_id, is_active=True)
        item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)

        item = _wishlist_queryset(request.user).get(pk=item.pk)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            WishlistItemSerializer(item, context={"request": request}).data, status=response_status
        )


class WishlistItemDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        # Scoped to the current user at the queryset level -- another
        # user's wishlist item 404s rather than 403ing, same reasoning
        # as apps.cart.views.CartItemDetailView.
        item = get_object_or_404(WishlistItem.objects.filter(user=request.user), pk=pk)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WishlistCheckView(APIView):
    """GET /wishlist/check/?product=<id> -- lets the frontend show a
    filled/empty heart on a product page without fetching the entire
    wishlist. Deliberately separate from the cart/product APIs (see
    master spec step 14 -- wishlist and cart/catalog stay decoupled)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Validated through a serializer rather than reading
        # request.query_params directly and handing it straight to the
        # ORM -- a non-numeric `?product=` would otherwise reach
        # WishlistItem.objects.filter(product_id=...) and raise an
        # uncaught ValueError (a 500), not a clean 400.
        serializer = WishlistCheckSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data["product"]

        is_wishlisted = WishlistItem.objects.filter(user=request.user, product_id=product_id).exists()
        return Response({"is_wishlisted": is_wishlisted})
