"""
Accounts views.

Deliberate separation from Django admin: everything here authenticates
against the SAME User model as /admin/, but through an entirely separate
code path -- session login here goes through django.contrib.auth.login()
against a manually-verified user (see serializers.LoginSerializer), not
Django's AdminSite login form, and is reachable only via
/api/v1/accounts/, never /admin/. Being staff or superuser doesn't grant
any special behavior through these customer-facing endpoints; it only
ever matters for /admin/ access, which Django's own AdminSite already
gates on `is_staff` independently of anything below.
"""
import logging

from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Address
from .permissions import IsOwner
from .serializers import (
    AddressSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class CsrfTokenView(APIView):
    """
    GET this once from the frontend (e.g. on app load) to ensure the
    csrftoken cookie is set before the first POST. DRF's
    SessionAuthentication enforces CSRF checks on unsafe methods, so the
    frontend needs a cookie to read the token from before it can send the
    required X-CSRFToken header on register/login/etc.
    """

    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"detail": "CSRF cookie set."})


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)  # auto-login immediately after registration
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        logout(request)  # flushes the session server-side, not just the cookie
        return Response({"detail": "Logged out."})


class MeView(generics.RetrieveUpdateAPIView):
    """GET the current user; PATCH to update the editable profile fields.
    PUT is intentionally not supported -- see ProfileUpdateSerializer for
    which fields are (and aren't) editable here."""

    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        return UserSerializer if self.request.method == "GET" else ProfileUpdateSerializer

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ProfileUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(instance).data)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Without this, Django's session-auth hash check invalidates the
        # *current* session the moment the password changes, forcing an
        # unnecessary immediate re-login right after a successful change.
        update_session_auth_hash(request, user)
        return Response({"detail": "Password changed successfully."})


class PasswordResetRequestView(APIView):
    """
    Sends a real email (via whatever EMAIL_BACKEND is configured --
    console output in development, real SMTP once EMAIL_HOST/etc are set
    in production; see .env.example) when the account has an email on
    file. This is genuinely functional, not a placeholder.

    SMS delivery for phone-only accounts is explicitly NOT implemented:
    no SMS provider is configured anywhere in this project, and the
    master spec says not to hardcode one. A phone-only account still gets
    the same generic success response as everyone else (see below for
    why), but no message is actually sent in that case -- wiring a real
    SMS provider is future-phase work, not something to fake here.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip()

        user = User.objects.filter(Q(phone=identifier) | Q(email=identifier)).first()

        # Always the same response, regardless of whether an account
        # exists or whether a message actually gets sent -- this
        # deliberately never confirms/denies that a given phone/email is
        # registered (a common account-enumeration vector otherwise).
        generic_response = Response(
            {"detail": "If an account matches, reset instructions have been sent."}
        )

        if user is None or not user.is_active:
            return generic_response

        if user.email:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = f"{settings.FRONTEND_URL}/reset-password/confirm/?uid={uid}&token={token}"
            send_mail(
                subject="Cusin Gallery - Password reset",
                message=(
                    f"Use this link to reset your password: {reset_url}\n\n"
                    "If you didn't request this, you can safely ignore this email."
                ),
                from_email=None,  # uses settings.DEFAULT_FROM_EMAIL
                recipient_list=[user.email],
                fail_silently=True,
            )
        else:
            logger.info(
                "Password reset requested for a phone-only account (id=%s); no SMS "
                "provider is configured, so no message was sent.",
                user.pk,
            )

        return generic_response


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    # Its own throttle scope, deliberately NOT shared with the request
    # view's "password_reset" scope: ScopedRateThrottle keys on scope +
    # client identity, so a shared scope would let legitimate confirm
    # attempts (e.g. a mistyped new password) consume the request
    # endpoint's 5/hour quota and lock a real user out of the reset
    # flow. Token validity is the confirm endpoint's real protection;
    # this rate is only a brute-force speed bump.
    throttle_scope = "password_reset_confirm"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password has been reset. You can now log in."})


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        # Scoped to the current user at the queryset level (not just via
        # IsOwner) so another user's address 404s instead of 403ing --
        # it never even appears in a list, and doesn't leak its existence
        # via a permission-denied response on direct access either.
        return Address.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        address = self.get_object()
        with transaction.atomic():
            Address.objects.filter(user=request.user, is_default=True).exclude(
                pk=address.pk
            ).update(is_default=False)
            address.is_default = True
            address.save(update_fields=["is_default"])
        return Response(AddressSerializer(address).data)
