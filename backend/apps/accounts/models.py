"""
Accounts models.

AUTH_USER_MODEL is set to "accounts.User" from Phase 1 onward (see
config/settings/base.py) -- see that phase's notes for why the model had
to exist before its business fields were ready.

Phase 2 added:
    - User.phone (plain data field)
    - Address (recipient_name, phone, province, city, address,
      postal_code, unit, building_number, is_default, ...)

Phase 3 (Authentication and accounts) adds:
    - User.email is now nullable with a conditional (partial) unique
      constraint, matching the same pattern already used for `phone` --
      see the class docstring below for why.
    - Real registration/login/logout/profile/password endpoints (see
      serializers.py, views.py, urls.py).
    - Address CRUD endpoints, scoped to the authenticated user.

Authentication decision (documented in full in
config/settings/base.py's REST_FRAMEWORK comment): session + CSRF, not
token/JWT. `USERNAME_FIELD` deliberately stays `username` (unchanged from
AbstractUser) rather than being switched to `phone` or `email` -- not
because phone-based login isn't wanted (it is: see LoginSerializer in
serializers.py, which accepts phone or email), but because actually
changing USERNAME_FIELD requires overhauling the user manager and
re-deriving uniqueness/authentication semantics from AbstractBaseUser, a
change this project has no way to verify end-to-end without a working
Django install (see the repeated "Honesty note" sections in the README).
Instead, registration sets `username = phone` directly -- phone numbers
already satisfy Django's default username character rules (digits and a
leading `+` are both allowed) -- and the login endpoint looks a user up
by phone/email manually rather than by going through USERNAME_FIELD at
all. This gets the desired customer-facing behaviour (log in with phone
or email) without touching the lower-level, harder-to-verify machinery.
Django admin login at /admin/ is completely unaffected either way -- it
still authenticates staff by `username`/password through Django's own
built-in login view, entirely separate from the customer-facing API
endpoints below (see views.py's module docstring for more on this
separation).
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel

phone_validator = RegexValidator(
    regex=r"^\+?\d{7,15}$",
    message="Enter a valid phone number (digits only, optionally prefixed with +).",
)


class User(AbstractUser):
    """
    Custom user model.

    `phone` stays nullable at the database level (not NOT NULL) even
    though customer self-registration requires it (enforced in
    RegisterSerializer, not here) -- making it a hard DB requirement now
    would risk breaking any staff/superuser account already created via
    `createsuperuser` in an earlier phase's local setup, since that
    command doesn't ask for phone. Application-level "required for
    customers" and database-level "always present" are different
    guarantees, and only the former is safe to add without a real
    database in front of me to check against.

    `email` is nullable with a conditional unique constraint (see Meta)
    for the same reason `phone` already was in Phase 2: Django's
    AbstractUser.email is a plain (non-unique) CharField-based field, so
    two customers could otherwise register with the same email. A plain
    `unique=True` isn't enough on its own though -- with email staying
    optional for customers, multiple users leaving it blank would all
    store `''`, and Postgres treats two empty strings as duplicates
    (unlike two NULLs, which it treats as distinct) -- so a plain unique
    constraint would incorrectly reject the *second* customer who simply
    left email blank. RegisterSerializer normalizes a blank email to
    `None` before saving specifically so this constraint works as
    intended.
    """

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        validators=[phone_validator],
        help_text="Required for customer self-registration (enforced in RegisterSerializer); "
        "nullable here because staff/superuser accounts aren't required to have one.",
    )
    email = models.EmailField(
        "email address",
        blank=True,
        null=True,
        help_text="Optional for customers. See the class docstring for why this is nullable "
        "rather than a plain unique CharField.",
    )

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        constraints = [
            models.UniqueConstraint(
                fields=["email"], condition=Q(email__isnull=False), name="user_email_unique_when_set"
            ),
        ]

    def save(self, *args, **kwargs):
        # Normalize a blank email to NULL on EVERY creation path -- not
        # only RegisterSerializer (which already does this, see its
        # `email = validated_data.get("email") or None`). Without it, any
        # other path (Django admin, createsuperuser, shell, the test
        # helpers' create_user) stores '' for users without an email, and
        # the partial unique constraint above then rejects the SECOND
        # such user ('' is a duplicate of '' unlike NULL, per that
        # docstring). Keeping the normalization here makes the constraint
        # work as documented regardless of how the user is created.
        if self.email == "":
            self.email = None
        super().save(*args, **kwargs)


class Address(TimeStampedModel):
    """
    A saved shipping/billing address belonging to a user.

    Deliberately NOT referenced by FK from Order -- orders snapshot their
    shipping address as flat fields at checkout time (see apps.orders),
    so editing or deleting an Address here never rewrites the historical
    record of a past order. This model is only ever the *source* an order
    copies from, never something a placed order points back to.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses"
    )
    recipient_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, validators=[phone_validator])
    province = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address = models.TextField()
    postal_code = models.CharField(max_length=20)
    unit = models.CharField(max_length=20, blank=True)
    building_number = models.CharField(max_length=20, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Address"
        verbose_name_plural = "Addresses"
        ordering = ["-is_default", "-created_at"]
        indexes = [
            models.Index(fields=["user"], name="addr_user_idx"),
        ]
        constraints = [
            # At most one default address per user, enforced at the
            # database level (a partial unique index) rather than only in
            # application code, which a bulk update or a future bug could
            # bypass.
            models.UniqueConstraint(
                fields=["user"], condition=Q(is_default=True), name="addr_one_default_per_user"
            ),
        ]

    def __str__(self):
        return f"{self.recipient_name} - {self.city}"
