"""
Cart API routes, mounted at /api/v1/cart/ (see config/api_urls.py).

Filled in as of Phase 5 - Cart and wishlist.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.CartView.as_view(), name="cart"),
    path("merge/", views.CartMergeView.as_view(), name="cart-merge"),
    path("items/", views.CartItemCreateView.as_view(), name="cart-item-create"),
    path("items/<int:pk>/", views.CartItemDetailView.as_view(), name="cart-item-detail"),
]
