"""Shared factories for adminui tests (not a test module)."""
from django.contrib.auth import get_user_model

from apps.categories.models import Category
from apps.orders.models import Order, OrderItem
from apps.products.models import Product

User = get_user_model()

# Admin templates reference {% static %}; keep tests independent of a
# built manifest -- same convention as the rest of the repo.
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}

_counter = {"n": 0}


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def make_superuser(**overrides):
    defaults = {
        "username": _unique("+98900000"),
        "password": "a-strong-passw0rd!",
        "phone": "+989001110000",
    }
    defaults.update(overrides)
    return User.objects.create_superuser(**defaults)


def make_staff(permissions=(), **overrides):
    defaults = {
        "username": _unique("+98900111"),
        "password": "a-strong-passw0rd!",
        "phone": "+989001112222",
    }
    defaults.update(overrides)
    user = User.objects.create_user(is_staff=True, **defaults)
    from django.contrib.auth.models import Permission

    if permissions:
        codenames = [perm.split(".")[-1] for perm in permissions]
        user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return user


def make_customer(**overrides):
    phone = overrides.pop("phone", None) or _unique("+98912000")
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


def make_order(user=None, product=None, **overrides):
    """A minimal valid order with one item. Snapshot fields required."""
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
    return order
