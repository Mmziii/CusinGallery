"""
Product filtering, per master spec section 12. Uses django_filters
(already installed and wired as the default filter backend since Phase 1
-- see config/settings/base.py's REST_FRAMEWORK), not a hand-rolled
query-param parser.
"""
import django_filters
from django import forms
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone

from .models import Product


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    """?ids=1,2,3 -- used by the guest cart to hydrate its lines with
    server-side names/prices (prices are NEVER trusted from the client)."""


TRUE_VALUES = ("1", "true", "yes", "on", "y", "t")
FALSE_VALUES = ("0", "false", "no", "off", "n", "f")


class RelaxedBooleanSelect(forms.NullBooleanSelect):
    """Reads 1/true/yes/on and 0/false/no/off as real booleans.

    Django's NullBooleanSelect only maps "true"/"false"/"True"/"False" (and
    the widget's own "2"), so a link asking for `?on_sale=1` produced
    "unknown" -> None and the filter was skipped entirely: «مشاهده همه»
    under the daily-deals band showed the whole shop (measured live:
    on_sale=1 -> 160 products, on_sale=true -> 19). Unrecognised or empty
    values keep the old no-op behaviour instead of erroring.
    """

    def value_from_datadict(self, data, files, name):
        raw = data.get(name)
        if raw is not None:
            token = str(raw).strip().lower()
            if token in TRUE_VALUES:
                return "true"
            if token in FALSE_VALUES:
                return "false"
        return super().value_from_datadict(data, files, name)


class RelaxedBooleanField(forms.NullBooleanField):
    widget = RelaxedBooleanSelect


class RelaxedBooleanFilter(django_filters.BooleanFilter):
    """Boolean query parameter accepting 1/0, true/false and yes/no."""

    field_class = RelaxedBooleanField


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
    # «مشاهده همه» under the daily-deals band: /shop/?on_sale=true (1/yes
    # also accepted). A product is on sale when its compare-at price beats
    # its selling price -- the same signal apps/products/pricing.py derives
    # `is_on_sale` from -- OR while an ACTIVE daily deal undercuts it: the
    # deal is what makes those cards show a struck-through price, so they
    # belong in the same result list.
    on_sale = RelaxedBooleanFilter(method="filter_on_sale")

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
        """?on_sale=true/1/yes keeps only discounted products; false/0/no
        (or anything unrecognised) leaves the catalog untouched.

        "Discounted" covers both signals the storefront renders as a
        struck-through price: a compare-at price above the selling price, or
        a daily deal that is active *right now* (same window as
        apps/banners/views.py and pricing.active_daily_deals_prefetch).
        """
        if not value:
            return queryset
        from apps.banners.models import DailyDeal

        now = timezone.now()
        active_deal = DailyDeal.objects.filter(
            product_id=OuterRef("pk"),
            is_active=True,
            starts_at__lte=now,
            ends_at__gt=now,
        )
        return queryset.filter(Q(compare_at_price__gt=F("price")) | Exists(active_deal))
