"""
Products serializers.
"""
from rest_framework import serializers

from . import pricing
from .models import Brand, Product, ProductAttributeValue, ProductImage, ProductVariant


class BrandSerializer(serializers.ModelSerializer):
    # Part R2: tile_image is exposed like product images (original + WebP
    # variants) so the home page brand tiles can use responsive sources.
    tile_image = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "logo", "is_featured", "display_order", "tile_image"]

    def get_tile_image(self, obj):
        from apps.core.image_files import media_url

        if not obj.tile_image:
            return None
        return {
            "image": obj.tile_image.url,
            "webp_400": media_url(obj.webp_400),
            "webp_800": media_url(obj.webp_800),
            "webp_1200": media_url(obj.webp_1200),
        }


class CategoryMiniSerializer(serializers.Serializer):
    """
    Deliberately not apps.categories.serializers.CategorySerializer --
    that one includes `product_count`, which requires its own annotation
    and isn't needed (or cheap to compute) when a category is just
    nested inside a product payload. A small local serializer keeps this
    app decoupled from categories' internals rather than importing and
    special-casing that serializer's fields.
    """

    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.SlugField()


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "is_primary", "ordering", "webp_400", "webp_800", "webp_1200"]

    def to_representation(self, instance):
        # webp_* columns hold storage-relative paths; clients need URLs
        # (Part R1 media_url fix).
        from apps.core.image_files import media_url

        data = super().to_representation(instance)
        for key in ("webp_400", "webp_800", "webp_1200"):
            data[key] = media_url(data.get(key))
        return data


class ProductAttributeValueSerializer(serializers.ModelSerializer):
    attribute = serializers.CharField(source="attribute.name", read_only=True)
    attribute_slug = serializers.CharField(source="attribute.slug", read_only=True)

    class Meta:
        model = ProductAttributeValue
        fields = ["id", "attribute", "attribute_slug", "value"]


class PriceInfoSerializer(serializers.Serializer):
    """Serializes a pricing.PriceInfo dataclass -- see that module for
    what each field means and why compare_at_price / discount_percentage
    are independent signals."""

    price = serializers.IntegerField()
    compare_at_price = serializers.IntegerField(allow_null=True)
    discount_percentage = serializers.IntegerField()
    is_on_sale = serializers.BooleanField()
    discount_amount = serializers.IntegerField()


class ProductVariantSerializer(serializers.ModelSerializer):
    price_info = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    is_in_stock = serializers.SerializerMethodField()
    attribute_values = ProductAttributeValueSerializer(many=True, read_only=True)
    image = ProductImageSerializer(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id", "sku", "price_info", "stock_status", "is_in_stock",
            "is_active", "attribute_values", "image",
        ]

    def get_price_info(self, obj):
        return PriceInfoSerializer(pricing.price_info_for_variant(obj)).data

    def get_stock_status(self, obj):
        return pricing.stock_status_for(obj)

    def get_is_in_stock(self, obj):
        return obj.stock_quantity > 0


class ProductListSerializer(serializers.ModelSerializer):
    """
    Used for GET /products/. Deliberately lean: no description, no full
    image list, no variants -- those are detail-only (see
    ProductDetailSerializer) to keep list payloads small and avoid
    forcing a nested-list query per row. `primary_image` and `price_info`
    are the only computed fields, both O(1) against data the view's
    queryset already prefetched (see ProductViewSet.get_queryset) rather
    than issuing their own query per product.
    """

    category = CategoryMiniSerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    price_info = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    is_in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "short_description", "category", "brand",
            "price_info", "primary_image", "stock_status", "is_in_stock",
            "is_featured", "is_new", "is_best_seller",
        ]

    def get_price_info(self, obj):
        return PriceInfoSerializer(pricing.price_info_for_product(obj)).data

    def get_primary_image(self, obj):
        # Relies on the view's queryset having prefetched `images`
        # ordered so the primary one sorts first (see
        # ProductViewSet.get_queryset) -- this reads from that prefetch
        # cache via list indexing, not a fresh query per product.
        images = list(obj.images.all())
        if not images:
            return None
        return ProductImageSerializer(images[0], context=self.context).data

    def get_stock_status(self, obj):
        return pricing.stock_status_for(obj)

    def get_is_in_stock(self, obj):
        return obj.stock_quantity > 0


class ProductDetailSerializer(ProductListSerializer):
    """
    Used for GET /products/{slug}/. Adds everything a single-product page
    needs that the list view deliberately omits for payload-size and
    query-cost reasons.
    """

    images = ProductImageSerializer(many=True, read_only=True)
    variants = serializers.SerializerMethodField()
    specifications = serializers.SerializerMethodField()
    related_products = serializers.SerializerMethodField()
    complements = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description", "sku", "images", "variants", "specifications",
            "related_products", "complements",
        ]

    def _active_variants(self, obj):
        # Cached per serializer instance (not a class-level/global cache)
        # -- safe because DRF constructs a fresh serializer instance per
        # request/object, and ProductDetailSerializer is only ever used
        # for a single-object retrieve (see ProductViewSet.get_serializer_class),
        # never a list. Without this, get_variants and get_specifications
        # would each independently re-run the same query.
        if not hasattr(self, "_active_variants_cache"):
            self._active_variants_cache = list(
                obj.variants.filter(is_active=True).prefetch_related(
                    "attribute_values__attribute", "image"
                )
            )
        return self._active_variants_cache

    def get_variants(self, obj):
        # Inactive variants are excluded entirely (not shown as
        # disabled) -- see master spec section 8 and ProductVariant's
        # own is_active flag.
        return ProductVariantSerializer(self._active_variants(obj), many=True, context=self.context).data

    def get_specifications(self, obj):
        """
        Derived from the product's variants' attribute values (Phase 2's
        schema attaches ProductAttributeValue to ProductVariant, not
        directly to Product -- there is no separate product-level "spec
        sheet" table). Grouped by attribute name with duplicate values
        removed, e.g. a product with Color variants Red/Blue/Green
        produces {"attribute": "Color", "values": ["Red", "Blue", "Green"]}.
        A product with no variants has no specifications from this
        mechanism -- extending this with a dedicated product-level
        specifications model (independent of purchasable variant
        options) would be a reasonable future-phase schema addition if
        the store needs specs unrelated to any variant choice.
        """
        grouped = {}
        order = []
        for variant in self._active_variants(obj):
            for av in variant.attribute_values.all():
                key = av.attribute.name
                if key not in grouped:
                    grouped[key] = []
                    order.append(key)
                if av.value not in grouped[key]:
                    grouped[key].append(av.value)
        return [{"attribute": name, "values": grouped[name]} for name in order]

    def get_related_products(self, obj):
        # ONE extra query, only on this single-object detail view -- see
        # the class docstring. Deliberately not offered on the list
        # serializer, where it would be a genuine per-row N+1.
        related = (
            Product.objects.filter(category=obj.category, is_active=True)
            .exclude(pk=obj.pk)
            .select_related("category", "brand")
            .prefetch_related("images")
            .order_by("-is_best_seller", "-is_featured", "-created_at")[:6]
        )
        return ProductListSerializer(related, many=True, context=self.context).data

    def get_complements(self, obj):
        """Part R5 item 9: «پیشنهاد همراه» candidates for the product page.

        Manual complements win when present; otherwise the mined
        FrequentlyBoughtTogether pairs (best co_count first). In BOTH
        cases only ACTIVE, IN-STOCK products are ever returned -- the
        storefront never offers what it cannot sell. No bundle pricing
        or stock logic: each item keeps its own price/stock.
        """
        from .models import FrequentlyBoughtTogether, purchasable_products

        purchasable_ids = set(purchasable_products().values_list("id", flat=True))

        manual = [p for p in obj.complements.all() if p.id in purchasable_ids]
        if manual:
            candidates = manual
        else:
            fbt = (
                FrequentlyBoughtTogether.objects.filter(product=obj)
                .select_related("complement")
                .order_by("-co_count", "id")
            )
            candidates = [
                row.complement for row in fbt if row.complement_id in purchasable_ids
            ]
        candidates = candidates[:8]
        # Same lean payload shape as the product list so the storefront
        # can reuse ProductCard directly.
        return ProductListSerializer(
            candidates, many=True, context=self.context
        ).data
