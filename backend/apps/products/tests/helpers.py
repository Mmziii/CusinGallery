"""
Shared factory helpers for products tests. Not a test module itself.
"""
from apps.categories.models import Category
from apps.products.models import (
    Brand,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
)

_counter = {"n": 0}


def _unique(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def make_category(name=None, **overrides):
    name = name or _unique("Category")
    defaults = {"slug": _unique("category")}
    defaults.update(overrides)
    return Category.objects.create(name=name, **defaults)


def make_brand(name=None, **overrides):
    name = name or _unique("Brand")
    defaults = {"slug": _unique("brand")}
    defaults.update(overrides)
    return Brand.objects.create(name=name, **defaults)


def make_product(category=None, name=None, **overrides):
    category = category or make_category()
    name = name or _unique("Product")
    defaults = {
        "slug": _unique("product"),
        "sku": _unique("SKU"),
        "price": 100000,
    }
    defaults.update(overrides)
    return Product.objects.create(category=category, name=name, **defaults)


def make_image(product, **overrides):
    defaults = {"image": "products/test.jpg"}
    defaults.update(overrides)
    return ProductImage.objects.create(product=product, **defaults)


def make_attribute(name=None, **overrides):
    name = name or _unique("Attribute")
    defaults = {"slug": _unique("attribute")}
    defaults.update(overrides)
    return ProductAttribute.objects.create(name=name, **defaults)


def make_attribute_value(attribute=None, value=None, **overrides):
    attribute = attribute or make_attribute()
    value = value or _unique("Value")
    return ProductAttributeValue.objects.create(attribute=attribute, value=value, **overrides)


def make_variant(product, attribute_values=None, **overrides):
    defaults = {"sku": _unique("VARIANT-SKU"), "stock_quantity": 10}
    defaults.update(overrides)
    variant = ProductVariant.objects.create(product=product, **defaults)
    if attribute_values:
        variant.attribute_values.set(attribute_values)
    return variant
