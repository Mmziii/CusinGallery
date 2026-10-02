"""
Banners API routes, mounted at /api/v1/banners/ (see config/api_urls.py).

Filled in with the homepage-content work: active banners (list + detail
via the router) and the active daily deals with server-provided timing.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("", views.BannerViewSet, basename="banner")

urlpatterns = [
    path("daily-deals/", views.DailyDealListView.as_view(), name="daily-deal-list"),
] + router.urls
