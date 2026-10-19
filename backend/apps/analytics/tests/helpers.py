"""Shared factories for analytics tests (not a test module)."""
from django.contrib.auth import get_user_model

from apps.categories.models import Category
from apps.products.models import Product

User = get_user_model()

_counter = {"n": 0}


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def make_customer(**overrides):
    phone = overrides.pop("phone", None) or _unique("+98917")
    defaults = {"username": phone, "phone": phone, "password": "a-strong-passw0rd!"}
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def make_category(**overrides):
    defaults = {"name": _unique("دسته"), "slug": _unique("category")}
    defaults.update(overrides)
    return Category.objects.create(**defaults)


def make_product(category=None, **overrides):
    category = category or make_category()
    defaults = {
        "name": _unique("محصول"),
        "slug": _unique("product"),
        "sku": _unique("SKU"),
        "price": 100000,
        "stock_quantity": 10,
    }
    defaults.update(overrides)
    return Product.objects.create(category=category, **defaults)


def make_order(user=None, product=None, created_at=None, **overrides):
    """A minimal valid order with one item (mirrors the adminui helper)."""
    from apps.orders.models import Order, OrderItem

    user = user or make_customer()
    product = product or make_product()
    item_overrides = overrides.pop("item", {})
    defaults = {
        "user": user,
        "status": Order.Status.PENDING,
        "payment_status": Order.PaymentStatus.PAID,
        "subtotal": product.price,
        "total": product.price,
        "shipping_recipient_name": "سارا احمدی",
        "shipping_phone": "09121112233",
        "shipping_province": "تهران",
        "shipping_city": "تهران",
        "shipping_address": "خیابان ولیعصر، پلاک ۱۰",
        "shipping_postal_code": "1234567890",
        "shipping_method": "standard",
    }
    defaults.update(overrides)
    order = Order.objects.create(**defaults)
    item_defaults = {
        "order": order,
        "product": product,
        "product_name": product.name,
        "sku": product.sku,
        "unit_price": product.price,
        "quantity": 1,
        "total_price": product.price,
    }
    item_defaults.update(item_overrides)
    OrderItem.objects.create(**item_defaults)
    if created_at is not None:
        Order.objects.filter(pk=order.pk).update(created_at=created_at)
        order.refresh_from_db()
    return order


def make_event(event_type, *, created_at=None, **overrides):
    from ..models import Event

    defaults = {"event_type": event_type, "session_key": "session-aaaaaaaa"}
    defaults.update(overrides)
    if created_at is not None:
        defaults["created_at"] = created_at
    return Event.objects.create(**defaults)
