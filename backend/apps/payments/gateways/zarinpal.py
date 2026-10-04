"""
ZarinPal payment gateway adapter (Phase C - Real payments).

Implements the PaymentGateway contract (base.py) against ZarinPal's v4
REST API, per the official documentation:
https://www.zarinpal.com/docs/paymentGateway/connectToGateway

Endpoints
---------
    production (PAYMENT_ZARINPAL_SANDBOX=False):
        POST https://api.zarinpal.com/pg/v4/payment/request.json
        POST https://api.zarinpal.com/pg/v4/payment/verify.json
        customer redirect: https://www.zarinpal.com/pg/StartPay/{authority}
    sandbox (PAYMENT_ZARINPAL_SANDBOX=True):
        POST https://sandbox.zarinpal.com/pg/v4/payment/request.json
        POST https://sandbox.zarinpal.com/pg/v4/payment/verify.json
        customer redirect: https://sandbox.zarinpal.com/pg/StartPay/{authority}

The sandbox is a full test mode: any 36-character merchant id is
accepted and no real money moves, so the whole flow can be exercised
before the real merchant id exists. Switching sandbox <-> production
changes ONLY the hosts above; nothing else in this adapter or anywhere
in the project differs between the two modes.

Money
-----
This project stores whole Toman integers. The v4 API's `currency` field
exists exactly for this: every request here sends currency=IRT (Toman)
with the amount UNCHANGED, so no Toman<->Rial conversion (and its 10x
foot-gun) exists anywhere in the codebase.

Callback contract
-----------------
ZarinPal redirects the customer's browser back to the callback_url with
`?Authority=<authority>&Status=OK|NOK` appended. The Status parameter is
NOT trusted -- it only selects the branch:

    Status=OK   -> verify.json is called server-to-server and ONLY its
                   answer decides the outcome: code 100 = success.
                   Code 101 = "this transaction was already verified
                   successfully once" per ZarinPal's docs, i.e. still a
                   successful capture -- honoring it is what makes a
                   replayed callback (or a verify whose response was
                   lost) resolve correctly instead of stranding real
                   money in PENDING forever.
    Status=NOK  -> the gateway itself says the transaction failed or the
                   customer cancelled at its page. ZarinPal deliberately
                   does not distinguish the two, so this is reported as
                   `cancelled` (customer came back without paying -- a
                   normal, non-error outcome) and verify is NOT called,
                   exactly as ZarinPal instructs ("verify should only be
                   used when Status is OK").

Security notes
--------------
    - verify() sends OUR stored gateway_transaction_id and OUR stored
      amount (the snapshot taken at initiation) -- never values taken
      from the callback query string. The callback's own Authority is
      only cross-checked against the stored one.
    - The merchant id is server-side only; it never appears in the
      redirect URL or in any browser-visible value.
    - Network/HTTP/JSON problems raise GatewayError (the service layer
      keeps the attempt PENDING on verify -- the money state is unknown
      -- and records FAILED on initiate). Business refusals inside a
      well-formed verify response are returned as a normal non-success
      VerificationResult instead, because those ARE a definitive answer.

Adding another Iranian gateway later (IDPay, NextPay, ...) means writing
one more adapter file like this one and registering it in
gateways/__init__.py -- nothing else changes (see docs/PAYMENTS.md).
"""
import requests
from django.conf import settings

from .base import GatewayError, InitiateResult, PaymentGateway, VerificationResult

#: v4 API hosts. Sandbox and production differ ONLY by host.
API_HOST_PRODUCTION = "https://api.zarinpal.com"
API_HOST_SANDBOX = "https://sandbox.zarinpal.com"

#: Hosted payment page the customer's browser is redirected to.
PAY_PAGE_PRODUCTION = "https://www.zarinpal.com/pg/StartPay/"
PAY_PAGE_SANDBOX = "https://sandbox.zarinpal.com/pg/StartPay/"

#: v4 `currency` value for Toman (this project's money unit). Sent on
#: BOTH request and verify so the amount is interpreted identically in
#: both calls, whatever ZarinPal's default unit is.
CURRENCY_TOMAN = "IRT"

#: verify.json response codes that mean "money was captured":
#:   100 - verified now (first successful verify)
#:   101 - already verified before (ZarinPal's documented idempotent
#:         repeat-verify answer; still a successful transaction)
VERIFY_SUCCESS_CODES = (100, 101)


def _first(callback_data: dict, *keys) -> str:
    """
    First present, non-empty value among `keys` of the raw callback
    parameters, flattened to a string. ZarinPal sends PascalCase query
    parameters (Authority/Status); accepting the lowercase spellings too
    costs nothing and keeps the adapter robust against gateway-side
    changes and against test doubles.
    """
    for key in keys:
        value = callback_data.get(key)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return ""


class ZarinpalGateway(PaymentGateway):
    name = "zarinpal"

    def __init__(self, merchant_id=None, sandbox=None, timeout=None):
        """
        All configuration is normally read from Django settings at call
        time (so override_settings works in tests and no secret is ever
        captured at import time). The explicit constructor arguments
        exist only for direct unit-testing of the adapter.
        """
        self._merchant_id = merchant_id
        self._sandbox = sandbox
        self._timeout = timeout

    # --- configuration (env-driven; see .env.example + docs/PAYMENTS.md) ---

    @property
    def merchant_id(self) -> str:
        value = settings.PAYMENT_MERCHANT_ID if self._merchant_id is None else self._merchant_id
        value = (value or "").strip()
        if not value:
            raise GatewayError(
                "PAYMENT_MERCHANT_ID is not configured (required for the zarinpal gateway)."
            )
        return value

    @property
    def sandbox(self) -> bool:
        return settings.PAYMENT_ZARINPAL_SANDBOX if self._sandbox is None else bool(self._sandbox)

    @property
    def timeout(self):
        return settings.PAYMENT_GATEWAY_TIMEOUT if self._timeout is None else self._timeout

    @property
    def api_base(self) -> str:
        host = API_HOST_SANDBOX if self.sandbox else API_HOST_PRODUCTION
        return f"{host}/pg/v4/payment"

    @property
    def pay_page_base(self) -> str:
        return PAY_PAGE_SANDBOX if self.sandbox else PAY_PAGE_PRODUCTION

    # --- PaymentGateway interface -------------------------------------------

    def initiate(self, payment, callback_url: str) -> InitiateResult:
        if not callback_url:
            raise GatewayError(
                "No callback URL available (set PAYMENT_CALLBACK_URL or call through the API view)."
            )
        order = payment.order
        payload = {
            "merchant_id": self.merchant_id,
            "amount": payment.amount,
            "currency": CURRENCY_TOMAN,
            "callback_url": callback_url,
            "description": f"سفارش {order.order_number} — کازین گالری",
            "metadata": {
                "order_id": order.order_number,
                "mobile": order.shipping_phone or "",
            },
        }
        envelope = self._post(f"{self.api_base}/request.json", payload)
        errors = envelope.get("errors")
        if errors:
            # A business refusal of the payment request itself (bad
            # merchant id, invalid callback URL, ...). Per the base
            # contract this is a GatewayError: the service records the
            # attempt as FAILED and answers 502 -- the customer never
            # gets a redirect URL that cannot work.
            raise GatewayError(f"ZarinPal refused the payment request: {_error_message(errors)}")

        data = envelope.get("data")
        authority = str((data or {}).get("authority") or "").strip()
        if not authority:
            raise GatewayError("ZarinPal accepted the request but returned no authority.")
        return InitiateResult(
            gateway_transaction_id=authority,
            redirect_url=f"{self.pay_page_base}{authority}",
        )

    def verify(self, payment, callback_data: dict) -> VerificationResult:
        status_value = _first(callback_data, "Status", "status").upper()
        authority = _first(callback_data, "Authority", "authority")

        if not status_value:
            return VerificationResult(
                success=False,
                failure_reason="Callback is missing the gateway Status parameter.",
            )
        if authority and authority != payment.gateway_transaction_id:
            # Defensive: the service already looked this payment up by
            # its gateway transaction id, so a mismatch means the
            # callback is trying to talk about a different transaction.
            return VerificationResult(
                success=False,
                failure_reason="Callback authority does not match this payment.",
            )

        if status_value != "OK":
            # NOK (or anything else): failed or cancelled at the gateway
            # page. ZarinPal does not distinguish, and instructs NOT to
            # call verify for these -- see module docstring.
            return VerificationResult(
                success=False,
                cancelled=True,
                failure_reason="cancelled_or_failed_at_gateway",
            )

        payload = {
            "merchant_id": self.merchant_id,
            "amount": payment.amount,
            "currency": CURRENCY_TOMAN,
            "authority": payment.gateway_transaction_id,
        }
        envelope = self._post(f"{self.api_base}/verify.json", payload)

        errors = envelope.get("errors")
        if errors:
            # A definitive business answer ("this authority is unknown /
            # expired / not payable") -- NOT an infrastructure error, so
            # it resolves the attempt as failed rather than raising.
            return VerificationResult(
                success=False,
                failure_reason=f"ZarinPal verification refused: {_error_message(errors)}"[:255],
            )

        data = envelope.get("data") or {}
        code = data.get("code")
        if code in VERIFY_SUCCESS_CODES:
            return VerificationResult(
                success=True,
                gateway_ref_id=str(data.get("ref_id") or ""),
                card_pan=str(data.get("card_pan") or "")[:32],
                card_fingerprint=str(data.get("card_hash") or "")[:64],
                extra={
                    "code": code,
                    "fee": data.get("fee"),
                    "fee_type": data.get("fee_type"),
                },
            )
        return VerificationResult(
            success=False,
            failure_reason=(
                f"ZarinPal verification returned code {code}"
                + (f": {data.get('message')}" if data.get("message") else "")
            )[:255],
        )

    # --- HTTP plumbing -------------------------------------------------------

    def _post(self, url: str, payload: dict) -> dict:
        """
        POST JSON to ZarinPal and return the parsed response body.

        Raises GatewayError ONLY for environmental problems -- network
        failure/timeout, non-200 HTTP status, malformed JSON. Business
        outcomes (the envelope's `errors` object) are returned to the
        caller untouched so initiate() and verify() can interpret them
        differently (refusal vs. definitive negative answer).
        """
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
        except requests.exceptions.RequestException as exc:
            # Never include exception detail beyond its class name: some
            # requests exceptions embed the URL with query data, and the
            # message ends up stored on Payment.failure_reason.
            raise GatewayError(
                f"ZarinPal could not be reached ({type(exc).__name__})."
            ) from exc

        if response.status_code != 200:
            raise GatewayError(f"ZarinPal returned HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError as exc:
            raise GatewayError("ZarinPal returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise GatewayError("ZarinPal returned an unexpected response shape.")
        return body


def _error_message(errors) -> str:
    """
    Human-readable message from a ZarinPal v4 `errors` value. The API
    sends either an object {"code": -9, "message": "...", "validations":
    [...]} or (in older/edge responses) an empty list when there is no
    error -- anything falsy means "no errors" and never reaches here.
    """
    if isinstance(errors, dict):
        code = errors.get("code")
        message = str(errors.get("message") or "").strip()
        validations = errors.get("validations")
        detail = ""
        if isinstance(validations, list) and validations:
            detail = " " + "; ".join(str(v) for v in validations)[:200]
        return f"[{code}] {message}{detail}".strip()
    return str(errors)[:255]
