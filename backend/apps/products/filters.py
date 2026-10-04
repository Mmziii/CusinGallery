"""
Product filtering, per master spec section 12. Uses django_filters
(already installed and wired as the default filter backend since Phase 1
-- see config/settings/base.py's REST_FRAMEWORK), not a hand-rolled
query-param parser.
"""
import django_filters

from .models import Product


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    """?ids=1,2,3 -- used by the guest cart to hydrate its lines with
    server-side names/prices (prices are NEVER trusted from the client)."""


class ProductFilter(django_filters.FilterSet):
    ids = NumberInFilter(field_name="id", lookup_expr="in")
    category = django_filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    brand = django_filters.CharFilter(field_name="brand__slug", lookup_expr="iexact")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    is_featured = django_filters.BooleanFilter(field_name="is_featured")
    is_new = django_filters.BooleanFilter(field_name="is_new")
    is_best_seller = django_filters.BooleanFilter(field_name="is_best_seller")

    class Meta:
        model = Product
        fields = ["category", "brand", "min_price", "max_price", "in_stock", "is_featured", "is_new", "is_best_seller"]

    def filter_in_stock(self, queryset, name, value):
        return queryset.filter(stock_quantity__gt=0) if value else queryset.filter(stock_quantity=0)
