"""
Product filtering, per master spec section 12. Uses django_filters
(already installed and wired as the default filter backend since Phase 1
-- see config/settings/base.py's REST_FRAMEWORK), not a hand-rolled
query-param parser.
"""
import django_filters
from django.db.models import F

from .models import Product


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    """?ids=1,2,3 -- used by the guest cart to hydrate its lines with
    server-side names/prices (prices are NEVER trusted from the client)."""


class ProductFilter(django_filters.FilterSet):
    ids = NumberInFilter(field_name="id", lookup_expr="in")
    category = django_filters.CharFilter(method="filter_category")
    brand = django_filters.CharFilter(method="filter_brand")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    is_featured = django_filters.BooleanFilter(field_name="is_featured")
    is_new = django_filters.BooleanFilter(field_name="is_new")
    is_best_seller = django_filters.BooleanFilter(field_name="is_best_seller")
    # «مشاهده همه» under the daily-deals band: /shop/?on_sale=1. A product
    # is on sale when its compare-at price beats its selling price -- the
    # same signal apps/products/pricing.py derives `is_on_sale` from.
    on_sale = django_filters.BooleanFilter(method="filter_on_sale")

    class Meta:
        model = Product
        fields = ["category", "brand", "min_price", "max_price", "in_stock", "is_featured", "is_new", "is_best_seller"]

    def filter_category(self, queryset, name, value):
        from apps.categories.tree import category_subtree_ids

        return queryset.filter(category_id__in=category_subtree_ids(value))

    def filter_brand(self, queryset, name, value):
        return queryset.filter(brand__slug__iexact=value, brand__is_active=True)

    def filter_in_stock(self, queryset, name, value):
        return queryset.filter(stock_quantity__gt=0) if value else queryset.filter(stock_quantity=0)

    def filter_on_sale(self, queryset, name, value):
        """?on_sale=true keeps only discounted products; any other value
        (including false) leaves the catalog untouched."""
        if not value:
            return queryset
        return queryset.filter(compare_at_price__gt=F("price"))
