"""
Reviews views.

Same session + CSRF auth as everywhere else. Three surfaces:
    - public, read-only: approved reviews for a product + rating summary
    - authenticated write: create a review (PENDING until moderated)
    - owner-only: view/edit/delete one's OWN review (any status, so a
      customer can see their own pending/rejected submission)

Duplicate prevention rides the model's unique constraint (one review per
user per product) -- the create view catches the IntegrityError and turns
it into a clean 400 rather than a 500.
"""
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Review
from .serializers import ReviewCreateSerializer, ReviewSerializer, ReviewUpdateSerializer


class ProductReviewListView(generics.ListAPIView):
    """GET /reviews/product/<product_id>/ -- APPROVED reviews only,
    newest first. Pending/rejected submissions are never public."""

    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return (
            Review.objects.filter(
                product_id=self.kwargs["product_id"], status=Review.Status.APPROVED
            )
            .select_related("user")
            .order_by("-created_at")
        )


class ProductReviewSummaryView(APIView):
    """GET /reviews/product/<product_id>/summary/ -- aggregate rating
    computed from APPROVED reviews only (a pending review must not move
    a product's public score before moderation)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        approved = Review.objects.filter(product_id=product_id, status=Review.Status.APPROVED)
        stats = approved.aggregate(average_rating=Avg("rating"), count=Count("id"))
        distribution = {
            str(rating): 0 for rating in range(1, 6)
        }
        for row in approved.values("rating").annotate(n=Count("id")):
            distribution[str(row["rating"])] = row["n"]

        average = stats["average_rating"]
        return Response(
            {
                "product_id": product_id,
                "count": stats["count"],
                "average_rating": round(average, 2) if average is not None else None,
                "distribution": distribution,
            }
        )


class ReviewCreateView(generics.CreateAPIView):
    """POST /reviews/ -- authenticated. Creates a PENDING review;
    is_verified_purchase is computed server-side."""

    serializer_class = ReviewCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            # Savepoint so the unique-constraint IntegrityError (a
            # duplicate review) rolls back cleanly without poisoning the
            # surrounding transaction.
            with transaction.atomic():
                review = serializer.save()
        except IntegrityError:
            return Response(
                {"non_field_errors": ["You have already reviewed this product."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET / PATCH / DELETE /reviews/<id>/ -- scoped to the reviewer's OWN
    review (404 for anyone else's, so existence isn't leaked). Because a
    customer may legitimately need to see their own not-yet-approved
    review, this does NOT filter by status -- ownership is the gate.
    """

    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Review.objects.filter(user=self.request.user).select_related("user", "product")

    def get_serializer_class(self):
        return ReviewUpdateSerializer if self.request.method == "PATCH" else ReviewSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ReviewUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        return Response(ReviewSerializer(review).data)


class MyReviewsView(generics.ListAPIView):
    """GET /reviews/mine/ -- the caller's own reviews in every status
    (their account page shows what's pending/approved/rejected)."""

    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Review.objects.filter(user=self.request.user)
            .select_related("user", "product")
            .order_by("-created_at")
        )
