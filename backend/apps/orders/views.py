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
from django.conf import settings
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
            # product__images feeds OrderItemSerializer.product_image
            # (Part R1) from the prefetch cache -- no per-item query.
            Prefetch(
                "items",
                queryset=OrderItem.objects.select_related("product", "variant").prefetch_related(
                    "product__images"
                ),
            )
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


class ShippingMethodsView(APIView):
    """
    GET /orders/shipping-methods/ -- the selectable shipping methods and
    their current cost/delivery-window configuration, so checkout UIs can
    render the selector (including per-method cost for the shopper's
    subtotal and the free-shipping threshold) without hardcoding any
    shipping number in frontend code. Public, read-only, and cheap: it
    only reads settings.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from . import shipping

        methods = shipping.get_shipping_methods()
        return Response(
            {
                "default": shipping.DEFAULT_METHOD,
                # Part 2: 0 means the gift-wrap option is hidden entirely.
                "gift_wrap_fee": settings.GIFT_WRAP_FEE,
                "methods": [
                    {"id": method_id, **config} for method_id, config in methods.items()
                ],
            }
        )


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


class InvoiceView(APIView):
    """GET /orders/<pk>/invoice/ (Part 2): a print-optimized invoice for
    the CALLING customer's own PAID order. Everything else -- someone
    else's order, or an unpaid/cancelled one -- is a plain 404, so the
    endpoint enumerates nothing.

    Shipped as print-optimized HTML with a print/save-as-PDF button on
    purpose: generating a real PDF server-side would require a font
    stack with verified Persian RTL shaping (Arabic joining, digit
    forms), which this project cannot verify renders correctly -- a
    broken-shaping PDF would be worse than the browser's own print
    pipeline, which handles Persian natively."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        from django.http import Http404
        from django.template.loader import render_to_string
        from django.http import HttpResponse

        from apps.core.models import SiteSettings

        from . import shipping

        order = Order.objects.filter(pk=pk, user=request.user).prefetch_related("items").first()
        if order is None or order.payment_status != Order.PaymentStatus.PAID:
            raise Http404
        html = render_to_string(
            "orders/invoice.html",
            {
                "order": order,
                "site": SiteSettings.load(),
                "shipping_method_label": shipping.method_label(order.shipping_method),
            },
            request=request,
        )
        return HttpResponse(html)
