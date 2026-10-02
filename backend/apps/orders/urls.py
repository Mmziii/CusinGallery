"""
Orders API routes, mounted at /api/v1/orders/ (see config/api_urls.py).

Filled in as of Phase 6 - Checkout and orders.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.OrderListView.as_view(), name="order-list"),
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    # Concrete paths MUST stay above the <int:pk>/ catch-all below.
    path("shipping-methods/", views.ShippingMethodsView.as_view(), name="shipping-methods"),
    path("<int:pk>/", views.OrderDetailView.as_view(), name="order-detail"),
]
