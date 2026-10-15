"""Template helpers for the store's own contact/branding values.

A seeded SiteSettings row holds instructions to the owner, not content
(``+98 21 0000 0000``, «[نشانی واقعی فروشگاه را از پنل مدیریت وارد کنید]»).
Printing those verbatim on an invoice or in an e-mail tells the customer
a lie, so every template surface runs the value through this filter
first: real values pass, placeholders become "".
"""

from django import template

from apps.core.placeholders import clean_value

register = template.Library()


@register.filter(name="no_placeholder")
def no_placeholder(value):
    """Return ``value`` for display, or "" when it is a placeholder."""
    return clean_value(value)
