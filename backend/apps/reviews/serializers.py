"""
Reviews serializers.

Read/write split mirrors the rest of the API:
    - ReviewSerializer        public, read-only (approved reviews only)
    - ReviewCreateSerializer  authenticated write; is_verified_purchase is
                              COMPUTED server-side, never a client field
    - ReviewUpdateSerializer  owner edits their own (rating/title/body)
"""
from rest_framework import serializers

from apps.core.serializers import NullToBlankTextMixin

from . import services
from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    """Public representation of an APPROVED review. The reviewer's
    username is exposed deliberately (storefront attribution); no other
    account detail leaks."""

    username = serializers.CharField(source="user.username", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)

    class Meta:
        model = Review
        fields = [
            "id", "product", "product_name", "product_slug", "username",
            "rating", "title", "body", "is_verified_purchase", "status",
            "created_at",
        ]
        read_only_fields = fields


class ReviewCreateSerializer(NullToBlankTextMixin, serializers.Serializer):
    """
    Input for POST /reviews/. Carries NO is_verified_purchase and NO
    status field -- moderation state and purchase verification are both
    decided by the backend (see services.has_verified_purchase and the
    model's default PENDING status). Sending those keys does nothing.
    """

    product_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    body = serializers.CharField(required=False, allow_blank=True, default="")

    def create(self, validated_data):
        from apps.products.models import Product

        user = self.context["request"].user
        product = Product.objects.filter(pk=validated_data["product_id"], is_active=True).first()
        if product is None:
            raise serializers.ValidationError({"product_id": ["این محصول در دسترس نیست."]})

        return Review.objects.create(
            product=product,
            user=user,
            rating=validated_data["rating"],
            title=validated_data.get("title", ""),
            body=validated_data.get("body", ""),
            is_verified_purchase=services.has_verified_purchase(user, product),
            status=Review.Status.PENDING,
        )


class ReviewUpdateSerializer(NullToBlankTextMixin, serializers.ModelSerializer):
    """Owner editing their own review. Status and is_verified_purchase
    are NOT writable here -- moderation stays with staff (admin), and
    verification stays computed. Editing re-submits the review for
    moderation (back to PENDING), same as a fresh submission."""

    class Meta:
        model = Review
        fields = ["rating", "title", "body"]

    def save(self, **kwargs):
        self.instance.status = Review.Status.PENDING
        return super().save(**kwargs)
