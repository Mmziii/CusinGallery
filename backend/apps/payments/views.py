"""
Payments views (Phase 7 - Payment architecture).

Three kinds of endpoints, three very different security postures:

    POST /payments/initiate/      customer-facing, session-authenticated,
                                  ownership-checked -- starts an attempt.

    *    /payments/callback/      gateway-facing. The customer's browser
                                  arrives here redirected by the gateway;
                                  nothing about the request is trusted --
                                  the outcome is decided by
                                  services.handle_callback asking the
                                  gateway to verify, never by these
                                  parameters alone, and never by the
                                  session.

    GET  /payments/mock-gateway/<authority>/
                                  the mock gateway's stand-in for a real
                                  PSP's hosted payment page (only mounted
                                  while the mock gateway is in use).
"""
import logging

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .gateways.mock import build_signed_callback_link
from .models import Payment
from .serializers import InitiatePaymentSerializer, PaymentSerializer
from .services import PaymentError, handle_callback, initiate_payment

logger = logging.getLogger("payments")


def _resolve_callback_url(request) -> str:
    """
    Absolute URL of this backend's callback endpoint. Built from the
    incoming request when possible so it is correct on whatever origin
    the deployment serves the API from (plain localhost in development,
    the Nginx edge in production, a reverse-proxied preview host, ...)
    -- settings.PAYMENT_CALLBACK_URL remains the fallback for programmatic
    calls without a request.
    """
    if request is not None:
        try:
            return request.build_absolute_uri(reverse("payment-callback"))
        except Exception:  # pragma: no cover - extremely defensive
            logger.exception("Could not build callback URL from request; using settings.")
    return settings.PAYMENT_CALLBACK_URL


class InitiatePaymentView(APIView):
    """
    POST /payments/initiate/ -- body: {"order_id": <one of my unpaid
    orders>}. Returns the new payment attempt plus the URL the frontend
    must redirect the browser to.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "payment_initiate"

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = initiate_payment(
                request.user,
                serializer.validated_data["order_id"],
                callback_url=_resolve_callback_url(request),
            )
        except PaymentError as exc:
            return Response(exc.errors, status=exc.http_status)

        return Response(
            {
                "payment": PaymentSerializer(result["payment"]).data,
                "redirect_url": result["redirect_url"],
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentDetailView(RetrieveAPIView):
    """
    GET /payments/{id}/ -- one payment attempt, scoped to attempts on the
    requesting user's own orders (404, not 403, for anyone else's, same
    pattern as orders). The payment-result page uses this to show the
    authoritative outcome after the gateway redirect lands.
    """

    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Payment.objects.filter(order__user=self.request.user)
            .select_related("order")
        )


@method_decorator(csrf_exempt, name="dispatch")
class PaymentCallbackView(APIView):
    """
    The gateway's return point. GET for browser redirects (what Iranian
    PSPs and the mock gateway use); POST accepted too, CSRF-exempt,
    because a server-to-server gateway notification carries no session
    and no CSRF token by definition. Both go through the exact same
    verification path.

    The response is always a redirect to the frontend's payment-result
    page -- the browser is standing on a backend URL with nothing to
    render; the result page then fetches the authoritative payment state
    through the normal authenticated API.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # outcome never depends on the session

    def get(self, request):
        return self._process(request)

    def post(self, request):
        return self._process(request)

    def _process(self, request):
        callback_data = dict(request.query_params.dict())
        body = request.data
        if hasattr(body, "dict"):  # QueryDict (form-encoded gateway POST)
            body = body.dict()
        if isinstance(body, dict):
            for key, value in body.items():
                # Gateway payloads can arrive with repeated keys; flatten
                # to the last value, same as request.query_params.dict().
                if isinstance(value, (list, tuple)):
                    value = value[-1] if value else ""
                callback_data[key] = value

        try:
            payment = handle_callback(callback_data)
        except PaymentError as exc:
            logger.warning("Rejected payment callback: %s", exc.errors)
            return HttpResponseRedirect(self._result_url(None, fallback_status="failed"))

        outcome = {
            Payment.Status.SUCCESS: "success",
            Payment.Status.FAILED: "failed",
            Payment.Status.CANCELLED: "cancelled",
            Payment.Status.PENDING: "pending",
        }[payment.status]
        return HttpResponseRedirect(self._result_url(payment.pk, fallback_status=outcome))

    @staticmethod
    def _result_url(payment_id, fallback_status):
        base = f"{settings.FRONTEND_URL.rstrip('/')}/payment/result/"
        if payment_id is None:
            return f"{base}?status={fallback_status}"
        return f"{base}{payment_id}/?status={fallback_status}"


class MockGatewayPageView(APIView):
    """
    The mock gateway's "hosted payment page": a tiny server-rendered page
    standing in for a real PSP's checkout page. Shows the amount and two
    links -- Pay and Cancel -- that follow the signed callback URL, which
    is exactly the protocol a real gateway redirect implements. Rendered
    by Django directly (no DRF serialization), plain HTML.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, authority):
        # Only meaningful while the mock gateway is the configured one;
        # with a real PSP selected, its own hosted page plays this role
        # and this view just bounces to the storefront.
        if (settings.PAYMENT_GATEWAY or "mock").strip().lower() != "mock":
            return HttpResponseRedirect(f"{settings.FRONTEND_URL.rstrip('/')}/")

        payment = (
            Payment.objects.filter(gateway_transaction_id=authority)
            .select_related("order")
            .first()
        )
        callback_url = _resolve_callback_url(request)
        context = {
            "payment": payment,
            "pay_url": build_signed_callback_link(callback_url, authority, "ok") if payment else "",
            "cancel_url": build_signed_callback_link(callback_url, authority, "cancelled") if payment else "",
        }
        return render(request, "payments/mock_gateway_page.html", context)
