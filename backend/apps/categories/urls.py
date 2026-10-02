"""
Categories API routes, mounted at /api/v1/categories/ (see config/api_urls.py).

Filled in as of Phase 4 - Products & Catalog.
"""
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet

router = DefaultRouter()
router.register("", CategoryViewSet, basename="category")

urlpatterns = router.urls
