"""
Payments API routes, mounted at /api/v1/payments/ (see config/api_urls.py).

Filled in as of Phase 7 - Payment architecture. The callback endpoint is
ALSO mounted at the site root (/payment/callback/) by config/urls.py so
the documented PAYMENT_CALLBACK_URL default works as-is; both paths run
the exact same view.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("initiate/", views.InitiatePaymentView.as_view(), name="payment-initiate"),
    path("callback/", views.PaymentCallbackView.as_view(), name="payment-callback"),
    path(
        "mock-gateway/<str:authority>/",
        views.MockGatewayPageView.as_view(),
        name="mock-gateway-page",
    ),
    path("<int:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
]
