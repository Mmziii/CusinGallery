"""
Discounts API routes, mounted at /api/v1/discounts/ (see config/api_urls.py).

Filled in with the coupon work: a single validation endpoint -- the
actual APPLICATION of a coupon happens inside checkout (see
apps.orders.services._apply_coupon), never through a separate client
call that a malicious frontend could skip or tamper with.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("coupons/validate/", views.ValidateCouponView.as_view(), name="coupon-validate"),
]
