"""
Shared test doubles for notifications tests. Not a test module itself.

FakeSMSProvider stands in for ANY provider (console/kavenegar/future):
services.py resolves the provider through get_provider() at delivery
time, so patching that one call site gives tests a provider that records
every send and can be told to fail -- no network, no credentials, and
the real service-layer machinery (logs, masking, idempotency, error
containment) still runs for real.
"""
from unittest import mock

from apps.notifications.providers.base import SMSProviderError


class FakeSMSProvider:
    """Records sends; optionally raises `error` instead of sending."""

    name = "fake"

    def __init__(self, error=None, message_id="FAKE-MSG-1"):
        self.sent = []  # one dict per send: recipient/message/template/tokens
        self.error = error
        self.message_id = message_id

    def send(self, recipient, message="", template="", tokens=None):
        self.sent.append({
            "recipient": recipient,
            "message": message,
            "template": template,
            "tokens": dict(tokens or {}),
        })
        if self.error is not None:
            raise self.error
        return self.message_id


def install_fake_provider(testcase, error=None, message_id="FAKE-MSG-1",
                          also_patch=()):
    """
    Patch services.get_provider for the duration of `testcase` and return
    the FakeSMSProvider so tests can inspect what would have been sent.
    Callers that trigger delivery from modules importing get_provider
    under their own name (e.g. apps.products.back_in_stock) pass those
    import paths in `also_patch`.
    """
    fake = FakeSMSProvider(error=error, message_id=message_id)
    patchers = [mock.patch("apps.notifications.services.get_provider", return_value=fake)]
    patchers += [mock.patch(path, return_value=fake) for path in also_patch]
    for patcher in patchers:
        patcher.start()
        testcase.addCleanup(patcher.stop)
    return fake


def provider_error(text="provider exploded"):
    return SMSProviderError(text)
