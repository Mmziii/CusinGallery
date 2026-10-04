"""
Cart views.

Same authentication architecture as every other authenticated endpoint
in this project: session + CSRF (see config/settings/base.py's
REST_FRAMEWORK comment, and apps/accounts for the original decision) --
no second auth mechanism introduced here.
"""
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from . import services
from .models import CartItem
from .permissions import IsCartItemOwner
from .serializers import AddCartItemSerializer, CartSerializer, UpdateCartItemSerializer


class CartView(APIView):
    """GET the current user's cart (auto-created on first access -- a
    Cart row isn't created at registration, only when first needed);
    DELETE clears it (removes all items, keeps the Cart row itself)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart = services.get_or_create_cart(request.user)
        view = services.build_cart_view(cart)
        return Response(CartSerializer(view, context={"request": request}).data)

    def delete(self, request):
        cart = services.get_or_create_cart(request.user)
        services.clear_cart(cart)
        view = services.build_cart_view(cart)
        return Response(CartSerializer(view, context={"request": request}).data)


class CartItemCreateView(APIView):
    """POST /cart/items/ -- add an item, or increment the existing line
    for the same (product, variant) pair. See services.add_item for the
    full behavior (availability checks, locking, the increment rule)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.add_item(
                user=request.user,
                product_id=serializer.validated_data["product_id"],
                variant_id=serializer.validated_data.get("variant_id"),
                quantity=serializer.validated_data["quantity"],
            )
        except services.CartError as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)

        cart = services.get_or_create_cart(request.user)
        view = services.build_cart_view(cart)
        return Response(CartSerializer(view, context={"request": request}).data, status=status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    """PATCH updates quantity (0 removes the item); DELETE removes it
    outright. Both are scoped to the requesting user's own cart items
    only -- see get_object below."""

    permission_classes = [permissions.IsAuthenticated, IsCartItemOwner]

    def get_object(self, request, pk):
        # Scoped to the current user's cart at the queryset level (not
        # just via IsCartItemOwner) so another user's cart item 404s
        # instead of 403ing -- same reasoning as
        # apps.accounts.views.AddressViewSet.get_queryset: it never even
        # appears to exist from this user's point of view, and doesn't
        # leak its existence via a permission-denied response either.
        #
        # select_related: services.update_item_quantity accesses
        # cart_item.product and cart_item.variant directly -- without
        # this, each of those would be a separate lazy query.
        queryset = CartItem.objects.filter(cart__user=request.user).select_related("product", "variant")
        obj = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(request, obj)
        return obj

    def patch(self, request, pk):
        item = self.get_object(request, pk)
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.update_item_quantity(item, serializer.validated_data["quantity"])
        except services.CartError as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)

        cart = services.get_or_create_cart(request.user)
        view = services.build_cart_view(cart)
        return Response(CartSerializer(view, context={"request": request}).data)

    def delete(self, request, pk):
        item = self.get_object(request, pk)
        item.delete()
        cart = services.get_or_create_cart(request.user)
        view = services.build_cart_view(cart)
        return Response(CartSerializer(view, context={"request": request}).data)


class CartMergeView(APIView):
    """POST /cart/merge/ (Part 1): merge the browser's guest cart into
    the authenticated user's server cart. Idempotent per merge_token --
    see services.merge_guest_lines. The guest cart is cleared by the
    frontend ONLY after this answers successfully."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        lines = request.data.get("lines")
        merge_token = str(request.data.get("merge_token") or "")[:64]
        view, report = services.merge_guest_lines(
            request.user, lines, merge_token
        )
        return Response({
            "cart": CartSerializer(view, context={"request": request}).data,
            "report": report,
        }, status=status.HTTP_200_OK)
