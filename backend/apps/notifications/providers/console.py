"""
Console SMS provider (Phase D - Notifications).

Development/test-only provider, the SMS counterpart of the payments
MockGateway: it performs no HTTP at all and simply logs what WOULD have
been sent, so the whole notification flow (event triggers, idempotency,
NotificationLog rows, admin visibility) is exercisable locally without
any provider credentials.

Allowed ONLY in development/test: config/settings/production.py refuses
to boot with SMS_PROVIDER=console (or empty, which means the same) while
SMS_ENABLED is on -- exactly like the mock payment gateway.
"""
import logging

from .base import SMSProvider

logger = logging.getLogger("notifications")


class ConsoleSMSProvider(SMSProvider):
    name = "console"

    def send(self, recipient: str, message: str = "", template: str = "", tokens: dict | None = None) -> str:
        if template:
            body = f"[template={template} tokens={tokens or {}}]"
        else:
            body = message
        logger.info("CONSOLE SMS to %s: %s", recipient, body)
        # A fake but non-empty reference id, so NotificationLog rows from
        # development runs look like real ones.
        return "console"
