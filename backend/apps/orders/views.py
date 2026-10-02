"""
Orders views.

Same authentication architecture as every other authenticated endpoint
in this project: session + CSRF -- no second auth mechanism. Order
history is strictly ownership-scoped (see get_queryset on both list and
detail views below); there is no staff/admin-facing endpoint here at
all -- order management for staff happens through Django Admin
(apps/orders/admin.py), entirely separate from this customer-facing API,
same separation pattern established for every other app since Phase 3.
"""
from django.db.models import Prefetch
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, OrderItem
from .serializers import CheckoutSerializer, OrderSerializer
from .services import CheckoutError, checkout


def _order_queryset(user):
    # select_related/prefetch_related here (not per-item, not per-list-
    # row) so listing N orders, each with M items, costs a small fixed
    # number of queries -- not N+1 or N*M. See
    # apps/orders/tests/test_performance.py for the query-count
    # regression guard.
    return (
        Order.objects.filter(user=user)
        # select_related("coupon"): OrderSerializer exposes coupon_code;
        # without this each order row lazy-loads its coupon (N+1).
        .select_related("coupon")
        .prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.select_related("product", "variant"))
        )
    )


class OrderListView(generics.ListAPIView):
    """GET /orders/ -- the current user's own order history, newest
    first (Order.Meta.ordering, unchanged from Phase 2)."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _order_queryset(self.request.user)


class OrderDetailView(generics.RetrieveAPIView):
    """
    GET /orders/{id}/ -- a single order. Scoped to the current user's
    own orders at the queryset level (not just a permission check) so
    another user's order 404s instead of 403ing -- it doesn't exist from
    this user's point of view, same pattern as every other
    ownership-scoped endpoint in this project (addresses, cart items,
    wishlist items).
    """

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _order_queryset(self.request.user)


class CheckoutView(APIView):
    """
    POST /orders/checkout/ -- converts the current user's cart into a
    real Order. See apps.orders.services.checkout for the full behavior
    (availability re-validation, server-computed pricing, address
    resolution, transaction/locking, cart clearing).
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "checkout"

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            order = checkout(request.user, serializer.validated_data)
        except CheckoutError as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)

        # Re-fetch through the same optimized queryset used for
        # list/detail rather than serializing the bare `order` returned
        # by checkout() directly -- keeps exactly one code path
        # responsible for "how an Order is fully loaded for a response".
        order = _order_queryset(request.user).get(pk=order.pk)
        return Response(OrderSerializer(order, context={"request": request}).data, status=status.HTTP_201_CREATED)
