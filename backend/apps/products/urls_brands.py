"""
Brand API routes. Mounted at the top-level /api/v1/brands/ by
config/api_urls.py, deliberately NOT nested under /api/v1/products/ --
see that file's comment for why, and Brand's own model (still defined in
apps.products, per Phase 2 -- no separate "brands" app was created for
this, matching the instruction not to duplicate/restructure existing
apps unnecessarily).
"""
from rest_framework.routers import DefaultRouter

from .views import BrandViewSet

router = DefaultRouter()
router.register("", BrandViewSet, basename="brand")

urlpatterns = router.urls
