"""
SMS provider abstraction (Phase D - Notifications).

Deliberately the same shape as apps/payments/gateways: the rest of the
codebase depends ONLY on this module's interface, providers live one per
file, and the registry in providers/__init__.py selects one by name from
settings.SMS_PROVIDER (env-only). Adding another Iranian SMS provider
(Melipayamak, SMS.ir, ...) later means ONE new subclass file + ONE
registry line -- nothing else changes.

Reliability contract every implementation must uphold:
    - send() either returns the provider's message id (possibly "") or
      raises SMSProviderError. It must NEVER raise anything else and
      must NEVER block longer than settings.SMS_TIMEOUT seconds.
    - Credentials (API keys, sender lines) come from settings only and
      must never appear in error messages, logs, or NotificationLog rows
      (services.py masks recipients; providers must not embed secrets in
      SMSProviderError messages -- Kavenegar puts its API key in the URL,
      so its adapter is careful to never quote the URL back).
    - The service layer catches EVERYTHING anyway: a broken provider can
      degrade notifications but must never break checkout, payment
      verification, or admin actions (see services.py).
"""
import abc


class SMSProviderError(Exception):
    """
    The provider could not be reached or refused the send. This is the
    ONLY exception a provider implementation may raise; services.py
    converts it into a FAILED NotificationLog row plus an error log --
    never into a broken user-facing flow.
    """


class SMSProvider(abc.ABC):
    """Interface every SMS provider implementation must provide."""

    #: stable identifier stored in settings.SMS_PROVIDER -- must match
    #: the registry key.
    name: str = ""

    @abc.abstractmethod
    def send(self, recipient: str, message: str = "", template: str = "", tokens: dict | None = None) -> str:
        """
        Send one SMS to `recipient` (an Iranian mobile number as stored
        on the account, e.g. "+989121234567").

        Two delivery modes, mirroring how Iranian providers work:
          * template mode (preferred, `template` non-empty): the text
            lives in a pre-approved template in the provider panel;
            `tokens` carries the variable parts (e.g. {"token": "123456"}
            for Kavenegar's verify-lookup). Template sends usually work
            even without a dedicated sender line and are delivered as
            service messages.
          * direct mode (`message` non-empty): send this exact text,
            typically requires a configured sender line.

        Implementations decide which modes they support and must raise
        SMSProviderError with a clear message when asked for something
        they cannot do (e.g. direct send without a sender line).

        Returns the provider's message/reference id ("" if it doesn't
        expose one). Raises SMSProviderError on any failure.
        """
