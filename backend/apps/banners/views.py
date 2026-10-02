"""
Banners / Daily Deals views.

Read-only, public. Both endpoints apply the SAME "active now" filter on
the server -- an admin-created row only appears while is_active AND
within its own date window, and disappears the moment the window closes.
No fake/evergreen content: if nothing is active, the list is empty and
the frontend renders nothing for that section (the daily-deal countdown
is likewise real, driven by the per-deal ends_at).
"""
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.models import ProductImage

from .models import Banner, DailyDeal
from .serializers import BannerSerializer, DailyDealSerializer


def _now():
    return timezone.now()


class BannerViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /banners/ -- active banners within their date window, in
    admin-controlled order. Detail-by-id is exposed by the router but the
    storefront consumes the list."""

    serializer_class = BannerSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        now = _now()
        return Banner.objects.filter(
            is_active=True,
        ).filter(
            Q(start_date__isnull=True) | Q(start_date__lte=now),
            Q(end_date__isnull=True) | Q(end_date__gte=now),
        ).order_by("ordering", "-created_at")

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)


class DailyDealListView(APIView):
    """
    GET /banners/daily-deals/ -- the active daily deals, each carrying its
    real starts_at/ends_at so the frontend can render an honest countdown.
    `server_now` is returned alongside so the client can compute
    time-remaining without trusting its own clock.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        now = _now()
        deals = (
            DailyDeal.objects.filter(
                is_active=True,
                starts_at__lte=now,
                ends_at__gte=now,
                product__is_active=True,
            )
            .select_related("product", "product__category", "product__brand")
            .prefetch_related(
                Prefetch(
                    "product__images",
                    queryset=ProductImage.objects.order_by("-is_primary", "ordering"),
                )
            )
            .order_by("ends_at")
        )
        return Response(
            {
                "server_now": now.isoformat(),
                "results": DailyDealSerializer(deals, many=True, context={"request": request}).data,
            }
        )
