"""
Shared serializer-level validators for address-shaped data.

Extracted here (Phase 6) so apps.orders.serializers.CheckoutSerializer's
inline shipping-address fields can reuse the exact same postal-code rule
apps.accounts.serializers.AddressSerializer already established in
Phase 3, instead of a second, drifting copy of the same five lines --
per the instruction to avoid duplicated validation logic between apps.
Behavior is unchanged from the original Phase 3 implementation; this is
a pure extraction, not a rule change.
"""
from rest_framework import serializers


def validate_postal_code(value):
    # Light-touch validation only -- Iranian postal codes are
    # conventionally 10 digits, but this stays permissive (digits and
    # optional dashes/spaces, 5-12 chars) rather than hard-coding an
    # exact format that could reject legitimate edge cases (P.O. box
    # codes, older addresses, data entry variance).
    cleaned = value.replace("-", "").replace(" ", "")
    if not cleaned.isdigit() or not (5 <= len(cleaned) <= 12):
        raise serializers.ValidationError("Enter a valid postal code.")
    return value
