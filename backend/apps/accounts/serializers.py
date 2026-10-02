"""
Accounts serializers.

Covers registration, login, the authenticated user's profile, password
change/reset, and Address CRUD. See models.py's module docstring for the
authentication architecture decisions these implement (session + CSRF,
`username = phone` under the hood, phone-or-email login).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from . import validators
from .models import Address, phone_validator

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    """
    Customer self-registration. A plain Serializer, not a ModelSerializer
    -- the input shape (password + password_confirm) doesn't map 1:1 onto
    User's own fields, and `username` is derived internally rather than
    accepted as input (see models.py's module docstring for why).
    """

    phone = serializers.CharField(max_length=20, validators=[phone_validator])
    email = serializers.EmailField(required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        # Reuses Django's configured AUTH_PASSWORD_VALIDATORS (see
        # config/settings/base.py) instead of duplicating strength rules here.
        try:
            validate_password(attrs["password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        email = validated_data.get("email") or None  # '' -> None, see User model docstring
        user = User.objects.create_user(
            username=validated_data["phone"],
            phone=validated_data["phone"],
            email=email,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            password=validated_data["password"],
        )
        return user


class LoginSerializer(serializers.Serializer):
    """
    Accepts either phone or email as the identifier. Does NOT go through
    Django's authenticate()/auth backends -- the user is looked up
    directly and the password checked manually, then handed to
    django.contrib.auth.login() in the view (see models.py's module
    docstring for the full reasoning behind this choice).
    """

    identifier = serializers.CharField(help_text="Phone number or email address.")
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        identifier = attrs["identifier"].strip()
        password = attrs["password"]
        user = User.objects.filter(Q(phone=identifier) | Q(email=identifier)).first()

        # One generic message for "no such account" and "wrong password"
        # alike, so the response itself never confirms whether a given
        # phone/email is registered.
        if user is None or not user.check_password(password):
            raise serializers.ValidationError(
                "No account matches those credentials, or the password is incorrect."
            )
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")

        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation of the authenticated user. `username` is
    deliberately excluded -- it's an internal implementation detail
    (set to the user's phone at registration; see models.py), not
    something the frontend should display or rely on."""

    class Meta:
        model = User
        fields = [
            "id", "first_name", "last_name", "email", "phone",
            "is_staff", "date_joined", "last_login",
        ]
        read_only_fields = fields


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Used for PATCH /me/. Deliberately excludes `phone` -- changing the
    phone number a real e-commerce account logs in with should require
    re-verification (an SMS OTP flow), and no SMS provider is configured
    anywhere in this project (see PasswordResetRequestView's docstring
    for the same constraint). Phone changes are future-phase work once
    that infrastructure exists.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def validate_email(self, value):
        value = value or None
        if value:
            qs = User.objects.filter(email=value).exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("An account with this email already exists.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        user = self.context["request"].user
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Phone number or email address.")


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        generic_error = "Invalid or expired reset link."
        try:
            user_pk = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_pk)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError(generic_error)

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(generic_error)

        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})

        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})

        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class AddressSerializer(serializers.ModelSerializer):
    """
    Handles the single-default-address rule from the application side,
    matching (not replacing) the database-level partial unique constraint
    from Phase 2 (`addr_one_default_per_user`). Setting `is_default=True`
    here first atomically clears any other default address for the same
    user, so the create/update below never collides with that constraint.
    """

    class Meta:
        model = Address
        fields = [
            "id", "recipient_name", "phone", "province", "city", "address",
            "postal_code", "unit", "building_number", "is_default",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_postal_code(self, value):
        return validators.validate_postal_code(value)

    def create(self, validated_data):
        user = self.context["request"].user
        with transaction.atomic():
            if validated_data.get("is_default"):
                Address.objects.filter(user=user, is_default=True).update(is_default=False)
            return Address.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        with transaction.atomic():
            if validated_data.get("is_default"):
                Address.objects.filter(user=instance.user, is_default=True).exclude(
                    pk=instance.pk
                ).update(is_default=False)
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
        return instance
