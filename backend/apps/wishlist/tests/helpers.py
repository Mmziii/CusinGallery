"""
Shared factory helpers for wishlist tests. Not a test module itself.
"""
from django.contrib.auth import get_user_model

from apps.categories.models import Category
from apps.products.models import Product

User = get_user_model()

_counter = {"n": 0}


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def make_user(**overrides):
    phone = overrides.pop("phone", None) or f"+9892{_counter['n']:08d}"
    _counter["n"] += 1
    defaults = {"username": phone, "phone": phone, "password": "a-strong-passw0rd!"}
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def make_category(**overrides):
    defaults = {"name": _unique("Category"), "slug": _unique("category")}
    defaults.update(overrides)
    return Category.objects.create(**defaults)


def make_product(category=None, **overrides):
    category = category or make_category()
    defaults = {
        "name": _unique("Product"),
        "slug": _unique("product"),
        "sku": _unique("SKU"),
        "price": 100000,
        "stock_quantity": 10,
    }
    defaults.update(overrides)
    return Product.objects.create(category=category, **defaults)
