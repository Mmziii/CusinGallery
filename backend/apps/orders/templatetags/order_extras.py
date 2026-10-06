"""Persian-digit + Toman formatting for printable documents (Part 2)."""
from django import template

register = template.Library()

_FA = "۰۱۲۳۴۵۶۷۸۹"


@register.filter
def fa_digits(value):
    """1234 -> ۱۲۳۴ (non-digits pass through)."""
    return "".join(_FA[int(ch)] if ch.isdigit() else ch for ch in str(value))


@register.filter
def fa_toman(value):
    """1234567 -> ۱۲۳۴٬۵۶ (thousands grouping, Persian digits)."""
    try:
        grouped = format(int(value), ",")
    except (TypeError, ValueError):
        return str(value)
    return fa_digits(grouped).replace(",", "٬")
