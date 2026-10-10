"""
Shared factory helpers for reviews tests. Not a test module itself.

Creates real users/products, and where verified-purchase matters, a real
PAID order via the production checkout+payment path.
"""
from django.contrib.auth import get_user_model

from apps.cart.models import Cart, CartItem
from apps.categories.models import Category
from apps.orders import services as order_services
from apps.payments.gateways.mock import _sign
from apps.payments.services import handle_callback, initiate_payment
from apps.products.models import Product

User = get_user_model()

_counter = {"n": 0}

CALLBACK = "http://testserver/api/v1/payments/callback/"


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def make_user(**overrides):
    phone = overrides.pop("phone", None) or f"+9896{_counter['n']:08d}"
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
        "stock_quantity": 50,
    }
    defaults.update(overrides)
    return Product.objects.create(category=category, **defaults)


def _checkout_payload():
    return {
        "recipient_name": "Reviewer",
        "phone": "+989121234567",
        "province": "Tehran",
        "city": "Tehran",
        "address": "Valiasr St, No. 10",
        "postal_code": "1234567890",
        "building_number": "10", "unit": "3",
    }


def make_paid_order_for(user, product, quantity=1):
    """Buy `product` and take the order all the way to PAID."""
    cart, _ = Cart.objects.get_or_create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=quantity)
    order = order_services.checkout(user, _checkout_payload())
    payment = initiate_payment(user, order.pk, callback_url=CALLBACK)["payment"]
    handle_callback(
        {"authority": payment.gateway_transaction_id, "status": "ok", "sig": _sign(payment.gateway_transaction_id, "ok")}
    )
    return order


def make_unpaid_order_for(user, product, quantity=1):
    """Buy `product` but never pay -- must NOT count as a verified purchase."""
    cart, _ = Cart.objects.get_or_create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=quantity)
    return order_services.checkout(user, _checkout_payload())
