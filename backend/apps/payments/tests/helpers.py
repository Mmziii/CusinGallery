"""
Shared factory helpers for payments tests. Not a test module itself.

Orders are created through the REAL checkout service (cart -> order),
not by hand-building Order rows -- payment tests must exercise the same
unpaid-order objects the production flow produces.
"""
from django.contrib.auth import get_user_model

from apps.cart.models import Cart, CartItem
from apps.categories.models import Category
from apps.orders import services as order_services
from apps.products.models import Product

User = get_user_model()

_counter = {"n": 0}


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def make_user(**overrides):
    phone = overrides.pop("phone", None) or f"+9894{_counter['n']:08d}"
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


def add_to_cart(user, product, quantity=1):
    cart, _ = Cart.objects.get_or_create(user=user)
    return CartItem.objects.create(cart=cart, product=product, quantity=quantity)


def checkout_payload(**overrides):
    payload = {
        "recipient_name": "Pay Customer",
        "phone": "+989121234567",
        "province": "Tehran",
        "city": "Tehran",
        "address": "Valiasr St, No. 10",
        "postal_code": "1234567890",
        "building_number": "10", "unit": "3",
    }
    payload.update(overrides)
    return payload


def make_unpaid_order(user, product=None, quantity=1):
    """A real unpaid order via the production checkout service."""
    product = product or make_product()
    add_to_cart(user, product, quantity=quantity)
    return order_services.checkout(user, checkout_payload())
