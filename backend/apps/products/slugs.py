"""Stable Unicode URLs for brands created without an explicit slug."""
from django.utils.text import slugify


def unique_brand_slug(brand):
    max_length = brand._meta.get_field("slug").max_length
    base = slugify(brand.name, allow_unicode=True)[:max_length] or "brand"
    candidate = base
    suffix = 2
    existing = type(brand).objects.exclude(pk=brand.pk)
    while existing.filter(slug=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[:max_length - len(tail)]}{tail}"
        suffix += 1
    return candidate
