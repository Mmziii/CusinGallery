"""
SMS provider tests (Phase D): registry selection, the console provider,
and the Kavenegar adapter against a faked requests.post -- no network
anywhere. Mirrors the payments fake-HTTP approach: the test asserts the
exact URL/params that WOULD go to Kavenegar (including that the API key
never appears in error messages) and the mapping of every response shape
onto SMSProviderError / a returned message id.
"""
from unittest import mock

import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from ..providers import ConsoleSMSProvider, KavenegarProvider, get_provider
from ..providers.base import SMSProviderError

TEST_API_KEY = "KAVENEGAR-TEST-KEY-1234567890"
TEST_SENDER = "10008812345678"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON")
        return self._payload


def kavenegar_ok(messageid=8792343):
    return {"return": {"status": 200, "message": "success"}, "entries": {"messageid": messageid}}


def kavenegar_refused(status=401, message="account is not active"):
    return {"return": {"status": status, "message": message}, "entries": []}


class ProviderRegistryTests(SimpleTestCase):
    def test_empty_setting_selects_console_for_development(self):
        with override_settings(SMS_PROVIDER=""):
            self.assertIsInstance(get_provider(), ConsoleSMSProvider)

    def test_console_is_selectable_explicitly(self):
        with override_settings(SMS_PROVIDER="console"):
            self.assertIsInstance(get_provider(), ConsoleSMSProvider)

    def test_kavenegar_is_selectable_case_insensitively(self):
        with override_settings(SMS_PROVIDER=" KaveNegar "):
            self.assertIsInstance(get_provider(), KavenegarProvider)

    def test_unknown_provider_fails_loudly_with_instructions(self):
        with override_settings(SMS_PROVIDER="melipayamak"):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                get_provider()
        self.assertIn("kavenegar", str(ctx.exception))


class ConsoleProviderTests(SimpleTestCase):
    def test_console_logs_instead_of_sending(self):
        provider = ConsoleSMSProvider()
        with self.assertLogs("notifications", level="INFO") as logs:
            result = provider.send("+989121234567", message="سلام")
        self.assertEqual(result, "console")
        self.assertIn("+989121234567", logs.output[0])
        self.assertIn("سلام", logs.output[0])

    def test_console_supports_template_mode(self):
        with self.assertLogs("notifications", level="INFO") as logs:
            ConsoleSMSProvider().send("+989120000000", template="reset", tokens={"token": "123456"})
        self.assertIn("template=reset", logs.output[0])


@override_settings(KAVENEGAR_API_KEY=TEST_API_KEY, SMS_SENDER=TEST_SENDER, SMS_TIMEOUT=7)
class KavenegarAdapterTests(SimpleTestCase):
    def _send(self, response=None, exception=None, **kwargs):
        fake = FakeResponse(response) if not isinstance(response, FakeResponse) else response
        with mock.patch(
            "apps.notifications.providers.kavenegar.requests.post",
            side_effect=exception if exception else mock.Mock(return_value=fake),
        ) as post:
            result = KavenegarProvider().send(**kwargs)
        return post, result

    def test_direct_send_uses_sms_send_endpoint_with_sender_line(self):
        post, message_id = self._send(
            response=kavenegar_ok(messageid=111),
            recipient="+989121234567", message="سفارش شما ارسال شد",
        )
        url = post.call_args.args[0]
        self.assertEqual(url, f"https://api.kavenegar.com/v1/{TEST_API_KEY}/sms/send.json")
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["receptor"], "+989121234567")
        self.assertEqual(data["message"], "سفارش شما ارسال شد")
        self.assertEqual(data["sender"], TEST_SENDER)
        self.assertEqual(post.call_args.kwargs["timeout"], 7)  # settings.SMS_TIMEOUT
        self.assertEqual(message_id, "111")

    def test_template_send_uses_verify_lookup_with_tokens(self):
        post, message_id = self._send(
            response=kavenegar_ok(messageid=222),
            recipient="09121234567", template="cusin_reset",
            tokens={"token": "654321", "token2": ""},
        )
        url = post.call_args.args[0]
        self.assertEqual(url, f"https://api.kavenegar.com/v1/{TEST_API_KEY}/verify/lookup.json")
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["receptor"], "09121234567")
        self.assertEqual(data["template"], "cusin_reset")
        self.assertEqual(data["token"], "654321")
        self.assertNotIn("token2", data)  # empty tokens are dropped
        self.assertEqual(message_id, "222")

    def test_send_entries_list_shape_is_tolerated(self):
        _, message_id = self._send(
            response={"return": {"status": 200}, "entries": [{"messageid": 333}]},
            recipient="09120000000", message="x",
        )
        self.assertEqual(message_id, "333")

    def test_missing_api_key_raises_without_calling_the_network(self):
        with override_settings(KAVENEGAR_API_KEY=""):
            with mock.patch("apps.notifications.providers.kavenegar.requests.post") as post:
                with self.assertRaises(SMSProviderError) as ctx:
                    KavenegarProvider().send(recipient="09120000000", message="x")
        self.assertIn("KAVENEGAR_API_KEY", str(ctx.exception))
        post.assert_not_called()

    def test_direct_send_without_sender_line_raises(self):
        with override_settings(SMS_SENDER=""):
            with self.assertRaises(SMSProviderError) as ctx:
                KavenegarProvider().send(recipient="09120000000", message="x")
        self.assertIn("SMS_SENDER", str(ctx.exception))

    def test_send_with_neither_message_nor_template_raises(self):
        with self.assertRaises(SMSProviderError):
            KavenegarProvider().send(recipient="09120000000")

    def test_empty_recipient_raises(self):
        with self.assertRaises(SMSProviderError):
            KavenegarProvider().send(recipient="  ", message="x")

    def test_api_level_refusal_maps_to_provider_error_WITHOUT_leaking_the_key(self):
        with mock.patch(
            "apps.notifications.providers.kavenegar.requests.post",
            return_value=FakeResponse(kavenegar_refused(401, "account is not active")),
        ):
            with self.assertRaises(SMSProviderError) as ctx:
                KavenegarProvider().send(recipient="09120000000", message="x")
        message = str(ctx.exception)
        self.assertIn("401", message)
        self.assertIn("account is not active", message)
        # The API key travels in the URL -- it must never surface in an
        # error that ends up stored on a NotificationLog row.
        self.assertNotIn(TEST_API_KEY, message)
        self.assertNotIn("api.kavenegar.com", message)

    def test_network_timeout_maps_to_provider_error_without_leaking_the_key(self):
        with mock.patch(
            "apps.notifications.providers.kavenegar.requests.post",
            side_effect=requests.exceptions.ConnectTimeout(),
        ):
            with self.assertRaises(SMSProviderError) as ctx:
                KavenegarProvider().send(recipient="09120000000", message="x")
        message = str(ctx.exception)
        self.assertIn("ConnectTimeout", message)
        self.assertNotIn(TEST_API_KEY, message)

    def test_non_json_response_maps_to_provider_error(self):
        with mock.patch(
            "apps.notifications.providers.kavenegar.requests.post",
            return_value=FakeResponse(None, status_code=502),
        ):
            with self.assertRaises(SMSProviderError) as ctx:
                KavenegarProvider().send(recipient="09120000000", message="x")
        self.assertIn("non-JSON", str(ctx.exception))
