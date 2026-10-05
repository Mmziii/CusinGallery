"""
Frontend error-report capture endpoint (Part S3 item 9).

The storefront ships without a Sentry SDK; when VITE_SENTRY_DSN is set
its ErrorBoundary POSTs here, and the view forwards into the EXISTING
backend Sentry setup (settings.SENTRY_DSN + sentry_sdk). Tests pin the
whole contract: open access, size caps, throttle scope, log-only mode
when no DSN is configured, and real capture_message forwarding when one
is.
"""
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.core.testing import CacheIsolatedAPITestCase


class ReportFrontendErrorTests(CacheIsolatedAPITestCase):
    url = reverse("site-report-error")

    def test_anonymous_report_accepted_and_logged(self):
        """A logged-out visitor's crash report is accepted (202) and kept
        in the server log even with no Sentry DSN configured."""
        with override_settings(SENTRY_DSN=""), self.assertLogs("django", level="WARNING") as logs:
            response = self.client.post(
                self.url,
                {
                    "message": "TypeError: cannot read properties of null",
                    "component": "ProductDetailPage",
                    "url": "https://cusin.ir/products/x/",
                    "stack": "at render (...)",
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        # No DSN -> nothing forwarded, but the report still exists in logs.
        self.assertFalse(response.json()["forwarded"])
        self.assertTrue(any("frontend error report" in line for line in logs.output))

    def test_forwards_to_sentry_when_dsn_configured(self):
        """With SENTRY_DSN set the report is forwarded through the same
        sentry_sdk the backend already initializes."""
        with override_settings(SENTRY_DSN="https://fake@example.invalid/1"), mock.patch(
            "sentry_sdk.capture_message"
        ) as capture, mock.patch("sentry_sdk.set_context") as set_context:
            response = self.client.post(
                self.url,
                {"message": "Render crash", "component": "Header"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(response.json()["forwarded"])
        capture.assert_called_once()
        self.assertIn("Render crash", capture.call_args.args[0])
        set_context.assert_called_once()

    def test_message_required(self):
        response = self.client.post(self.url, {"component": "x"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message", response.json())

    def test_oversized_fields_capped(self):
        """Huge payloads can not flood the log/Sentry: fields are capped,
        not rejected (a crashing client can not be asked to fix them)."""
        with override_settings(SENTRY_DSN=""), self.assertLogs("django", level="WARNING"):
            response = self.client.post(
                self.url,
                {"message": "m" * 50000, "stack": "s" * 50000, "url": "u" * 5000},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_throttled(self):
        """The endpoint is public AllowAny, so it carries its own rate
        limit (30/hour) -- the 31st report inside the window is a 429."""
        for _ in range(30):
            response = self.client.post(self.url, {"message": "boom"}, format="json")
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        response = self.client.post(self.url, {"message": "boom"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
