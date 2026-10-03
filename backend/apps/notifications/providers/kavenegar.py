"""
Kavenegar SMS provider adapter (Phase D - Notifications).

Implements the SMSProvider contract against Kavenegar's v1 REST API
(https://kavenegar.com/rest.html):

    direct send   POST https://api.kavenegar.com/v1/{API_KEY}/sms/send.json
                  params: receptor, message, sender (the "sender line")
    template send POST https://api.kavenegar.com/v1/{API_KEY}/verify/lookup.json
                  params: receptor, template, token, token2, token3

    response      {"return": {"status": 200, "message": "..."},
                   "entries": {"messageid": 123} | [{"messageid": 123}, ...]}

`return.status` is the authoritative outcome (Kavenegar reports API-level
refusals -- bad key, no credit, unknown template -- inside a 200 HTTP
response); anything other than 200 is an SMSProviderError carrying
Kavenegar's own message.

Configuration (env-only, see both .env.example files):
    KAVENEGAR_API_KEY   the account API key -- SECRET. It travels in the
                        request URL (Kavenegar's API shape), so this
                        adapter never logs or quotes URLs, and error
                        messages carry only return.status/return.message.
    SMS_SENDER          the sender line number (e.g. 1000xxxx) for
                        direct sends. Required for direct mode; template
                        mode works without it.
    SMS_TEMPLATE_PASSWORD_RESET / SMS_TEMPLATE_ORDER_CONFIRMED /
    SMS_TEMPLATE_ORDER_SHIPPED
                        pre-approved template names in the Kavenegar
                        panel. When a template name for an event is
                        empty, the service falls back to direct mode
                        with a locally-composed Persian text.
    SMS_TIMEOUT         per-call HTTP timeout in seconds.
"""
import requests
from django.conf import settings

from .base import SMSProvider, SMSProviderError

API_BASE = "https://api.kavenegar.com/v1"


class KavenegarProvider(SMSProvider):
    name = "kavenegar"

    def send(self, recipient: str, message: str = "", template: str = "", tokens: dict | None = None) -> str:
        api_key = (settings.KAVENEGAR_API_KEY or "").strip()
        if not api_key:
            raise SMSProviderError("KAVENEGAR_API_KEY is not configured.")
        recipient = (recipient or "").strip()
        if not recipient:
            raise SMSProviderError("No recipient phone number for the SMS.")

        if template:
            url = f"{API_BASE}/{api_key}/verify/lookup.json"
            params = {"receptor": recipient, "template": template}
            for key, value in (tokens or {}).items():
                if value is not None and value != "":
                    params[key] = value
        else:
            if not message:
                raise SMSProviderError("Kavenegar send called with neither a template nor a message.")
            sender = (settings.SMS_SENDER or "").strip()
            if not sender:
                raise SMSProviderError(
                    "SMS_SENDER (sender line) is not configured -- required for direct "
                    "SMS sends, or set a template name for this event instead."
                )
            url = f"{API_BASE}/{api_key}/sms/send.json"
            params = {"receptor": recipient, "message": message, "sender": sender}

        return self._post(url, params)

    @staticmethod
    def _post(url: str, params: dict) -> str:
        """POST to Kavenegar and return its messageid. Raises
        SMSProviderError for anything environmental; error strings never
        contain the URL (which embeds the API key)."""
        try:
            response = requests.post(
                url, data=params, timeout=settings.SMS_TIMEOUT,
                headers={"Accept": "application/json"},
            )
        except requests.exceptions.RequestException as exc:
            raise SMSProviderError(f"Kavenegar could not be reached ({type(exc).__name__}).") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise SMSProviderError(
                f"Kavenegar returned a non-JSON response (HTTP {response.status_code})."
            ) from exc
        if not isinstance(body, dict):
            raise SMSProviderError("Kavenegar returned an unexpected response shape.")

        result = body.get("return") or {}
        status_code = result.get("status")
        if status_code != 200:
            raise SMSProviderError(
                f"Kavenegar refused the send (status {status_code}): {result.get('message') or 'unknown error'}"
            )

        # entries is an object for verify/lookup and a list for sms/send;
        # tolerate both and anything else (the send succeeded either way).
        entries = body.get("entries")
        if isinstance(entries, dict):
            return str(entries.get("messageid") or "")
        if isinstance(entries, list) and entries:
            first = entries[0]
            if isinstance(first, dict):
                return str(first.get("messageid") or "")
            return str(first)
        return ""
