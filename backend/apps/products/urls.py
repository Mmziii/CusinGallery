"""
Products API routes, mounted at /api/v1/products/ (see config/api_urls.py).

Filled in as of Phase 4 - Products & Catalog. Brand routes live in
urls_brands.py, mounted separately at /api/v1/brands/ by
config/api_urls.py -- see that file's comment for why.
"""
from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import BackInStockView, ProductViewSet

router = DefaultRouter()
router.register("", ProductViewSet, basename="product")

# Explicit path BEFORE the router: "back-in-stock/" would otherwise be
# swallowed by the router's <pk> detail pattern.
urlpatterns = [
    path("back-in-stock/", BackInStockView.as_view(), name="back-in-stock"),
] + router.urls
