"""
Customer password policy (Part 1).

Customers get ONLY two rules, on purpose:

  1. minimum 8 characters;
  2. ASCII-only -- Persian/Arabic characters (and Persian digits) are
     rejected with a clear Persian message telling the shopper to
     switch their keyboard to English. A password typed on a Persian
     keyboard looks identical in length but never matches what the
     shopper types later on an English keyboard (login forms, other
     devices), which is a support nightmare; rejecting it at creation
     time is the honest fix.

Deliberately NOT applied to customers: similarity, common-password and
all-numeric checks. An 8-digit numeric password (a phone-style PIN,
very common and memorable for this audience) is ACCEPTED. Django's
strict AUTH_PASSWORD_VALIDATORS remain configured globally and keep
protecting STAFF/SUPERUSER passwords (createsuperuser, admin change
forms) -- only the customer-facing serializers use this module.

Login never applies any of this: existing passwords are never locked
out by a policy change.
"""
from django.core.exceptions import ValidationError

MIN_LENGTH = 8

TOO_SHORT_MESSAGE = "رمز عبور باید حداقل ۸ کاراکتر باشد."
NON_ASCII_MESSAGE = (
    "رمز عبور نباید شامل حروف فارسی یا عربی باشد؛ کیبورد را روی انگلیسی بگذارید."
)


def validate_customer_password(password: str, user=None) -> None:
    """Raise ValidationError (Persian message) when `password` violates
    the customer policy. Signature mirrors Django's validators so it can
    be swapped in wherever they were used."""
    password = password or ""
    if len(password) < MIN_LENGTH:
        raise ValidationError(TOO_SHORT_MESSAGE)
    if any(ord(char) > 127 for char in password):
        raise ValidationError(NON_ASCII_MESSAGE)
