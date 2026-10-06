"""
Shared factory helpers for orders tests. Not a test module itself.
"""
from django.contrib.auth import get_user_model

from apps.accounts.models import Address
from apps.cart.models import Cart, CartItem
from apps.categories.models import Category
from apps.products.models import Product, ProductVariant

User = get_user_model()

_counter = {"n": 0}


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def make_user(**overrides):
    phone = overrides.pop("phone", None) or f"+9893{_counter['n']:08d}"
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


def make_variant(product=None, **overrides):
    product = product or make_product()
    defaults = {"sku": _unique("VARIANT-SKU"), "stock_quantity": 10}
    defaults.update(overrides)
    return ProductVariant.objects.create(product=product, **defaults)


def make_address(user, **overrides):
    defaults = {
        "recipient_name": "Sara Ahmadi",
        "phone": "+989121234567",
        "province": "Tehran",
        "city": "Tehran",
        "address": "Valiasr St, No. 10",
        "postal_code": "1234567890",
        # Part S5 item 6: a saved address has a plot and a unit now.
        "building_number": "10",
        "unit": "3",
    }
    defaults.update(overrides)
    return Address.objects.create(user=user, **defaults)


def add_to_cart(user, product, variant=None, quantity=1):
    cart, _ = Cart.objects.get_or_create(user=user)
    return CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=quantity)


def valid_checkout_payload(**overrides):
    payload = {
        "recipient_name": "Sara Ahmadi",
        "phone": "+989121234567",
        "province": "Tehran",
        "city": "Tehran",
        "address": "Valiasr St, No. 10",
        "postal_code": "1234567890",
        "unit": "3",  # Part S5 item 6: plot/unit are required
        "building_number": "10",
    }
    payload.update(overrides)
    return payload
