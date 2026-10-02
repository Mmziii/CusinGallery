"""
Wishlist API routes, mounted at /api/v1/wishlist/ (see config/api_urls.py).

Filled in as of Phase 5 - Cart and wishlist.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.WishlistListView.as_view(), name="wishlist"),
    path("items/", views.WishlistItemCreateView.as_view(), name="wishlist-item-create"),
    path("items/<int:pk>/", views.WishlistItemDetailView.as_view(), name="wishlist-item-detail"),
    path("check/", views.WishlistCheckView.as_view(), name="wishlist-check"),
]
