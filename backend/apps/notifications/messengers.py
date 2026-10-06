"""
Messenger channel adapters for OWNER alerts (Part R4 item 3).

Same adapter discipline as the SMS providers: one tiny base class, one
module per service, a registry, env-only credentials. These channels are
DISABLED BY DEFAULT -- a provider is only active when BOTH its bot token
AND chat id are set in env. Failures here must never break a business
flow: send() raises MessengerError, and the caller (services.py) catches
and logs everything.

Telegram: standard Bot API -- POST {base}/bot{token}/sendMessage with a
JSON body {"chat_id", "text"}. NOTE: Telegram is frequently filtered or
unreliable from servers inside Iran; treat it as best-effort.

Bale (بله): the domestic messenger's Bot API mirrors Telegram's method
names. Per the official docs (docs.bale.ai) the business API endpoint is
POST https://tapi.bale.ai/business/bot{token}/sendMessage with the same
{"chat_id", "text"} JSON body; community examples also use the older
https://tapi.bale.ai/bot{token}/sendMessage shape, which is why the base
URL is env-configurable (BALE_API_BASE). The endpoint shape was verified
against the public documentation only -- no live call is made from tests.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger("notifications")

HTTP_TIMEOUT_SECONDS = 10


class MessengerError(Exception):
    """Delivery failure towards a messenger bot API."""


class MessengerProvider:
    """Base class: name + token/chat_id + base_url; send(text) POSTs the
    Telegram-shaped sendMessage call."""

    name = "messenger"

    def __init__(self, token, chat_id, base_url):
        self.token = token
        self.chat_id = chat_id
        self.base_url = (base_url or "").rstrip("/")

    @property
    def enabled(self):
        return bool((self.token or "").strip() and str(self.chat_id or "").strip())

    def send(self, text: str) -> str:
        if not self.enabled:
            raise MessengerError(f"{self.name} messenger is not configured.")
        url = f"{self.base_url}/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text[:4096]}
        try:
            response = requests.post(url, json=payload, timeout=HTTP_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            # Never echo the URL (it contains the token).
            raise MessengerError(f"{self.name} send failed: {exc}") from exc
        if response.status_code >= 400:
            raise MessengerError(
                f"{self.name} API answered {response.status_code}."
            )
        return str(response.json().get("result", {}).get("message_id", ""))[:64]


class TelegramMessenger(MessengerProvider):
    name = "telegram"

    def __init__(self):
        super().__init__(
            settings.TELEGRAM_BOT_TOKEN,
            settings.TELEGRAM_CHAT_ID,
            settings.TELEGRAM_API_BASE,
        )


class BaleMessenger(MessengerProvider):
    name = "bale"

    def __init__(self):
        super().__init__(
            settings.BALE_BOT_TOKEN,
            settings.BALE_CHAT_ID,
            settings.BALE_API_BASE,
        )


def get_enabled_messengers():
    """The messenger providers actually configured (token + chat id). An
    empty list means owner alerts stay SMS/email-only."""
    return [provider for provider in (TelegramMessenger(), BaleMessenger()) if provider.enabled]
