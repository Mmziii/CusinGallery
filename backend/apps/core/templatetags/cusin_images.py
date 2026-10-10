"""
Part S4 item 1: the shared "no image" placeholder for Django-rendered
surfaces (the printable invoice today; any future server-rendered page can
use the same tag).

The storefront routes every product/category/brand image through
frontend/src/components/SmartImage.jsx; the markup below is its server-side
twin -- same warm-grey field, same brand mark at the same olive/.35
opacity -- so a missing image and a broken image look identical everywhere.
"""
from django import template
from django.utils.safestring import mark_safe

from apps.core.image_files import image_or_placeholder_html

register = template.Library()


@register.filter
def product_thumb(image, size=40):
    """{{ product.images.first|product_thumb }} -> <img> + shared placeholder."""
    return image_or_placeholder_html(image, width=int(size), height=int(size), radius=6)


@register.simple_tag
def image_ph(size=40):
    """{% image_ph 48 %} -> the placeholder on its own."""
    from apps.core.image_files import placeholder_html

    return mark_safe(placeholder_html(int(size), int(size)))
