"""
Banners serializers.

Both endpoints are public and read-only -- content is managed entirely in
Django admin. The daily-deal serializer embeds the catalog's own
ProductListSerializer so a deal renders with the exact same price/image
shape the storefront already uses, and adds the deal's own timing so the
frontend can build a REAL countdown (from ends_at) rather than a fake
one.
"""
from rest_framework import serializers

from apps.products.serializers import ProductListSerializer

from .models import Banner, DailyDeal


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = [
            "id", "title", "subtitle", "image", "cta_text", "cta_url",
            "ordering", "start_date", "end_date",
            "webp_400", "webp_800", "webp_1200",
        ]

    def to_representation(self, instance):
        # webp_* columns hold storage-relative paths; clients need URLs
        # (Part R1 media_url fix).
        from apps.core.image_files import media_url

        data = super().to_representation(instance)
        for key in ("webp_400", "webp_800", "webp_1200"):
            data[key] = media_url(data.get(key))
        return data


class DailyDealSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = DailyDeal
        fields = ["id", "product", "sale_price", "starts_at", "ends_at"]
