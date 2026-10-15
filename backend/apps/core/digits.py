def fa_digits(value):
    """Persian digits for customer-facing messages."""
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
