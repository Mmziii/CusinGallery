"""
Payment gateway abstraction (Phase 7 - Payment architecture).

The rest of the codebase (services, views, admin, tests) depends ONLY on
this module's interface -- never on any concrete gateway. Implementations
live one per file next to this one (mock.py for dev/test, zarinpal.py for
the real ZarinPal PSP as of Phase C); adding another Iranian gateway
(IDPay, NextPay, ...) means adding one new file that subclasses
PaymentGateway, one line in the registry in gateways/__init__.py, and
setting PAYMENT_GATEWAY in the environment. Nothing else in the project
changes -- same as the shipping abstraction in apps/orders/shipping.py,
which this deliberately mirrors.

Security contract every implementation must uphold (and that the mock
gateway honors too, so the flow is exercised for real):
    - initiate() returns the gateway's own transaction handle plus the
      URL the customer's browser is redirected to. No secret may appear
      in that URL.
    - verify() is called server-side with the RAW callback parameters.
      Success must be decided by the gateway's own verification (a real
      PSP re-checks the transaction with its API; the mock validates an
      HMAC), NEVER by trusting a client-supplied "status" alone.
    - callback_url is passed to initiate() by the service layer (built
      from the incoming request, falling back to
      settings.PAYMENT_CALLBACK_URL) -- implementations must not guess it.
"""
import abc
from dataclasses import dataclass, field


@dataclass(frozen=True)
class InitiateResult:
    """What a gateway hands back when it accepts a payment request."""

    gateway_transaction_id: str
    redirect_url: str


@dataclass(frozen=True)
class VerificationResult:
    """
    Outcome of verifying a gateway callback.

    `cancelled` is kept separate from a plain failure: a customer
    pressing "cancel" at the gateway page is a normal, non-error outcome
    and is surfaced to the frontend differently from "the gateway
    rejected/failed this transaction" (see services.handle_callback).

    On success, gateways should also pass through whatever receipt data
    the PSP returns:
        gateway_ref_id      the PSP's final reference/receipt id,
        card_pan            the MASKED paying card number as the PSP
                            returns it (e.g. 603770******4281) -- never
                            a full PAN,
        card_fingerprint    the PSP-provided hash of the card (ZarinPal's
                            card_hash) -- a fingerprint for support and
                            reconciliation, not card data.
    All three are stored on the Payment row by services.handle_callback
    (empty when the gateway doesn't provide them, as the mock doesn't).
    """

    success: bool
    cancelled: bool = False
    gateway_ref_id: str = ""
    card_pan: str = ""
    card_fingerprint: str = ""
    failure_reason: str = ""
    extra: dict = field(default_factory=dict)


class GatewayError(Exception):
    """
    Raised when the gateway itself cannot be reached / misbehaves (as
    opposed to a normal "payment declined" verification outcome, which is
    expressed through VerificationResult). The service layer converts
    this into a failed payment attempt + a clear API error, never a 500
    with a traceback.
    """


class PaymentGateway(abc.ABC):
    """Interface every gateway implementation must provide."""

    #: stable identifier stored on Payment.gateway and selected via
    #: settings.PAYMENT_GATEWAY -- must match the registry key.
    name: str = ""

    @abc.abstractmethod
    def initiate(self, payment, callback_url: str) -> InitiateResult:
        """
        Register `payment` with the gateway and return the URL the
        customer's browser should be redirected to. Must raise
        GatewayError if the gateway cannot be reached or refuses the
        request; a normal "declined later" is NOT an error here.
        """

    @abc.abstractmethod
    def verify(self, payment, callback_data: dict) -> VerificationResult:
        """
        Decide, authoritatively, whether the callback means the payment
        succeeded. `callback_data` is the raw GET/POST parameters of the
        callback request. Implementations MUST re-verify against the
        gateway's own record (or, for the mock, its own signature) and
        must never return success merely because callback_data says so.
        """
