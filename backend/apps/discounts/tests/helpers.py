"""
Shared factory helpers for discounts tests. Not a test module itself.

build_cart_view() returns dicts of CartLineView dataclasses, so these
helpers construct minimal objects with the exact attributes
apps.discounts.services reads -- keeping coupon unit tests free of
cart/order plumbing while integration tests use the real pipeline.
"""
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.categories.models import Category
from apps.products.models import Product

from ..models import Coupon

User = get_user_model()

_counter = {"n": 0}


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def make_user(**overrides):
    phone = overrides.pop("phone", None) or f"+9895{_counter['n']:08d}"
    _counter["n"] += 1
    defaults = {"username": phone, "phone": phone, "password": "a-strong-passw0rd!"}
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def make_category(parent=None, **overrides):
    defaults = {"name": _unique("Category"), "slug": _unique("category"), "parent": parent}
    defaults.update(overrides)
    return Category.objects.create(**defaults)


def make_product(category=None, **overrides):
    category = category or make_category()
    defaults = {
        "name": _unique("Product"),
        "slug": _unique("product"),
        "sku": _unique("SKU"),
        "price": 100000,
        "stock_quantity": 50,
    }
    defaults.update(overrides)
    return Product.objects.create(category=category, **defaults)


def make_coupon(code=None, **overrides):
    defaults = {
        "code": code or _unique("CODE"),
        "discount_type": Coupon.DiscountType.PERCENTAGE,
        "percentage_value": 10,
    }
    defaults.update(overrides)
    return Coupon.objects.create(**defaults)


def make_line(product, quantity=1, is_available=True, line_total=None):
    """A CartLineView-shaped object for validate_and_calculate()."""
    if line_total is None:
        line_total = product.price * quantity
    item = SimpleNamespace(product_id=product.pk, product=product)
    return SimpleNamespace(item=item, is_available=is_available, line_total=line_total)


def make_cart_view(lines):
    subtotal = sum(line.line_total for line in lines if line.is_available)
    return {"lines": lines, "subtotal": subtotal, "total": subtotal, "item_count": len(lines)}


def add_to_cart(user, product, quantity=1):
    cart, _ = Cart.objects.get_or_create(user=user)
    return CartItem.objects.create(cart=cart, product=product, quantity=quantity)


def in_future(**kw):
    return timezone.now() + timezone.timedelta(**kw)


def in_past(**kw):
    return timezone.now() - timezone.timedelta(**kw)
