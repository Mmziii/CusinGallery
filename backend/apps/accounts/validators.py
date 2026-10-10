"""
Shared serializer-level validators for address-shaped data.

Used by apps.accounts.serializers.AddressSerializer and by
apps.orders.serializers.CheckoutSerializer's inline shipping-address
fields, so the exact same rules apply to a saved address and to a
one-off checkout address.

Part S1 (item 3) hardened these after the owner could not add an
address: Persian/Arabic digits are normalized to ASCII BEFORE
validation, the postal code must be exactly 10 digits, and the address
phone must be an Iranian mobile (09xxxxxxxxx) or landline (0 + area
code, 11 digits total). Validators RETURN the normalized form so the
database only ever stores clean ASCII digits.
"""
from rest_framework import serializers

#: Persian (U+06F0..) and Arabic-Indic (U+0660..) digits to ASCII.
_DIGITS_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(value):
    """Map Persian/Arabic digits to ASCII; other characters unchanged."""
    return (value or "").translate(_DIGITS_TO_ASCII)


def validate_postal_code(value):
    """Exactly 10 digits (dashes/spaces tolerated, Persian digits
    normalized). Returns the cleaned 10-digit string."""
    cleaned = normalize_digits(value).replace("-", "").replace(" ", "").strip()
    if not cleaned.isdigit() or len(cleaned) != 10:
        raise serializers.ValidationError("کد پستی باید دقیقاً ۱۰ رقم باشد.")
    return cleaned


def validate_address_phone(value):
    """Iranian phone: mobile 09xxxxxxxxx or landline 0 + area code
    (11 digits total). +98 / 0098 prefixes and Persian/Arabic digits are
    normalized to the plain 0... form. Returns the normalized number."""
    cleaned = normalize_digits(value).replace("-", "").replace(" ", "").strip()
    if cleaned.startswith("+98"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("0098"):
        cleaned = "0" + cleaned[4:]
    if cleaned.startswith("9") and len(cleaned) == 10:
        cleaned = "0" + cleaned
    if len(cleaned) == 11 and cleaned.isdigit() and cleaned.startswith("0"):
        return cleaned  # 09... mobile or 0<area-code>... landline
    raise serializers.ValidationError(
        "شماره تماس باید موبایل ایرانی (مانند 09123456789) یا تلفن ثابت با کد شهر (مانند 02112345678) باشد."
    )


#: Part S5 item 6: how long a plot number / unit may be.
MAX_PLOT_UNIT_LENGTH = 20

PLOT_UNIT_MESSAGES = {
    "building_number": "پلاک ساختمان را وارد کنید.",
    "unit": "واحد را وارد کنید. اگر واحد ندارید عدد ۰ را وارد کنید.",
}


def _clean_plot_unit(value, *, field):
    """Shared rule for the plot number (پلاک) and the unit (واحد):

    required (non-empty after trimming), at most MAX_PLOT_UNIT_LENGTH
    characters, and digits only -- Persian/Arabic digits are normalized to
    ASCII first, so «۱۲» is stored as "12". Returns the cleaned value.
    """
    label = "پلاک ساختمان" if field == "building_number" else "واحد"
    cleaned = normalize_digits(value).replace(" ", "").replace("-", "").strip()
    if not cleaned:
        raise serializers.ValidationError(PLOT_UNIT_MESSAGES[field])
    if len(cleaned) > MAX_PLOT_UNIT_LENGTH:
        raise serializers.ValidationError(
            f"{label} حداکثر {MAX_PLOT_UNIT_LENGTH} رقم می‌تواند باشد."
        )
    if not cleaned.isdigit():
        raise serializers.ValidationError(f"{label} باید فقط عدد باشد (مثلاً ۱۲).")
    return cleaned


def validate_building_number(value):
    """Part S5 item 6: the plot number is required and numeric."""
    return _clean_plot_unit(value, field="building_number")


def validate_unit(value):
    """Part S5 item 6: the unit is required too; «۰» means "no unit"."""
    return _clean_plot_unit(value, field="unit")
