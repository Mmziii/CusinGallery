"""
Mock payment gateway (Phase 7 - Payment architecture).

A fully-working, self-contained gateway used when no real PSP is
configured (settings.PAYMENT_GATEWAY empty or "mock"). It exists because
the payment FLOW -- initiation, redirect, callback, verification,
exactly-once inventory transition, duplicate-callback protection -- must
be implemented and tested end to end WITHOUT inventing credentials for a
real gateway, which the project explicitly forbids. This is not a fake
"everything succeeds" stub: it implements the full protocol, including
an HMAC-signed callback the verify step actually validates, a cancel
path, and rejection of tampered/unsigned callbacks.

Flow:
    1. initiate() mints an `authority` code and redirects the browser to
       the mock gateway's own page (served by apps.payments.views),
       which shows Pay / Cancel buttons -- standing in for a real PSP's
       hosted payment page.
    2. Whichever button the customer presses follows the callback URL
       with `authority`, `status`, and an HMAC signature computed with
       the gateway secret -- standing in for the signed redirect-back a
       real PSP produces.
    3. verify() recomputes the HMAC and only reports success when the
       signature is valid AND the status is "ok". A tampered or forged
       callback fails verification exactly like a real PSP would reject
       it server-side.

Gateway secret: PAYMENT_MERCHANT_ID if configured (the same env slot a
real gateway's merchant credentials will use), otherwise Django's
SECRET_KEY -- in both cases server-side only, never sent to the browser.
"""
import hashlib
import hmac
import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.urls import reverse

from .base import GatewayError, InitiateResult, PaymentGateway, VerificationResult


def _gateway_secret() -> str:
    return settings.PAYMENT_MERCHANT_ID or settings.SECRET_KEY


def _sign(authority: str, status: str) -> str:
    return hmac.new(
        _gateway_secret().encode(), f"{authority}:{status}".encode(), hashlib.sha256
    ).hexdigest()


def _base_url_of(callback_url: str) -> str:
    """scheme://netloc of the callback URL -- the mock gateway page is
    served by the same backend that receives callbacks, so its own URLs
    are built from the callback's origin. In production both live behind
    the same Nginx edge; locally it's the backend's own host/port."""
    parts = urlsplit(callback_url)
    return f"{parts.scheme}://{parts.netloc}"


def build_signed_callback_link(callback_url: str, authority: str, status: str) -> str:
    """
    The URL the mock gateway's hosted page sends the browser to when the
    customer presses Pay or Cancel -- callback URL + authority + status +
    HMAC signature. Lives here (not in the view) so the signing rule has
    exactly one home, shared by the page that builds links and verify()
    that checks them.
    """
    sep = "&" if "?" in callback_url else "?"
    return f"{callback_url}{sep}authority={authority}&status={status}&sig={_sign(authority, status)}"


class MockGateway(PaymentGateway):
    name = "mock"

    def initiate(self, payment, callback_url: str) -> InitiateResult:
        if not callback_url:
            raise GatewayError("PAYMENT_CALLBACK_URL is not configured.")
        authority = uuid.uuid4().hex
        page_url = reverse("mock-gateway-page", args=[authority])
        redirect_url = f"{_base_url_of(callback_url)}{page_url}"
        return InitiateResult(gateway_transaction_id=authority, redirect_url=redirect_url)

    def verify(self, payment, callback_data: dict) -> VerificationResult:
        def _first(value):
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ""
            return "" if value is None else str(value)

        authority = _first(callback_data.get("authority"))
        status = _first(callback_data.get("status"))
        provided_sig = _first(callback_data.get("sig"))

        if not authority or not status:
            return VerificationResult(
                success=False, failure_reason="Callback is missing required parameters."
            )
        if authority != payment.gateway_transaction_id:
            return VerificationResult(
                success=False, failure_reason="Callback authority does not match this payment."
            )
        if not hmac.compare_digest(provided_sig, _sign(authority, status)):
            return VerificationResult(
                success=False, failure_reason="Callback signature verification failed."
            )

        if status == "ok":
            # Deterministic per-authority receipt id -- mirrors a real
            # PSP handing back its own reference number on verification.
            ref_id = "MOCK-" + hashlib.sha256(authority.encode()).hexdigest()[:16].upper()
            return VerificationResult(success=True, gateway_ref_id=ref_id)
        if status == "cancelled":
            return VerificationResult(success=False, cancelled=True, failure_reason="cancelled_by_customer")
        return VerificationResult(success=False, failure_reason=f"Gateway reported status '{status}'.")
