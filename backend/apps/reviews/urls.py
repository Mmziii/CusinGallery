"""
Reviews API routes, mounted at /api/v1/reviews/ (see config/api_urls.py).

Filled in with the customer-reviews work: public approved-review listing
+ rating summary per product, authenticated creation, and owner-only
detail/update/delete plus a "my reviews" list.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.ReviewCreateView.as_view(), name="review-create"),
    path("mine/", views.MyReviewsView.as_view(), name="review-mine"),
    path("product/<int:product_id>/", views.ProductReviewListView.as_view(), name="product-review-list"),
    path(
        "product/<int:product_id>/summary/",
        views.ProductReviewSummaryView.as_view(),
        name="product-review-summary",
    ),
    path("<int:pk>/", views.ReviewDetailView.as_view(), name="review-detail"),
]
