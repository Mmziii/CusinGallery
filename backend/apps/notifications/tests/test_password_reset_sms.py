"""
Phone-only password reset end-to-end tests (Phase D).

Drives the REAL API endpoints (POST /accounts/password-reset/ and
/password-reset/confirm/) with the fake SMS provider and Django's locmem
mail backend, covering the full security contract:

* a 6-digit code is issued, delivered by SMS, hashed at rest;
* the code is single-use, expiring, and re-issuing invalidates the old one;
* unknown phone / wrong code / expired code / consumed code all answer
  with the SAME generic error (no enumeration, no oracle);
* the request endpoint is rate limited (5/hour) and never reveals whether
  an account exists or which channel was used;
* email accounts keep the existing link flow (and prefer it when both
  contact points exist);
* provider failure or SMS disabled degrades to a logged row and the same
  generic 200 -- the endpoint itself never breaks.
"""
from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import PhoneResetCode
from apps.core.testing import CacheIsolatedAPITestCase
from apps.notifications.models import NotificationLog
from apps.notifications.services import Events
from apps.payments.tests.helpers import make_user

from .helpers import install_fake_provider, provider_error


class PasswordResetSMSTestBase(CacheIsolatedAPITestCase):
    def setUp(self):
        self.request_url = reverse("password-reset-request")
        self.confirm_url = reverse("password-reset-confirm")

    def request_reset(self, identifier):
        return self.client.post(self.request_url, {"identifier": identifier}, format="json")

    def confirm_with_code(self, phone, code, password="brand-new-passw0rd!"):
        return self.client.post(
            self.confirm_url,
            {
                "phone": phone,
                "code": code,
                "new_password": password,
                "new_password_confirm": password,
            },
            format="json",
        )

    def issue_code_for(self, user):
        """Run the request endpoint with on-commit delivery executed and
        return the plaintext code the fake provider 'sent'."""
        fake = getattr(self, "fake", None)
        if fake is None:
            raise AssertionError("call install_fake_provider(self) first")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.request_reset(user.phone)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        sent_message = fake.sent[-1]["message"] if fake.sent else ""
        sent_token = (fake.sent[-1]["tokens"].get("token") if fake.sent else "") or ""
        # The plaintext code is what landed in the message (direct mode)
        # or the template token (template mode).
        row = PhoneResetCode.objects.get(user=user)
        for candidate in [sent_token] + [w for w in sent_message.replace(":", " ").split()]:
            candidate = candidate.strip().rstrip(".")
            if candidate.isdigit() and len(candidate) == 6 and row.matches(candidate):
                return candidate
        raise AssertionError(f"no 6-digit code found in fake SMS sends: {fake.sent}")


class PhoneOnlyResetFlowTests(PasswordResetSMSTestBase):
    def setUp(self):
        super().setUp()
        self.fake = install_fake_provider(self)
        self.user = make_user(phone="+989127000001", password="old-passw0rd!")

    def test_request_issues_a_hashed_expiring_code_and_sends_it_by_sms(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.request_reset(self.user.phone)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        row = PhoneResetCode.objects.get(user=self.user)
        # hashed at rest, expiring, unconsumed
        self.assertNotEqual(row.code_hash, "")
        self.assertGreater(row.expires_at, timezone.now())
        self.assertLessEqual(row.expires_at, timezone.now() + timedelta(minutes=15))
        self.assertIsNone(row.consumed_at)
        # delivered by SMS, 6 digits, to the account phone
        self.assertEqual(len(self.fake.sent), 1)
        sent = self.fake.sent[0]
        self.assertEqual(sent["recipient"], "+989127000001")
        self.assertTrue(any(part.strip().rstrip(".").isdigit() and len(part.strip().rstrip(".")) == 6
                            for part in sent["message"].replace(":", " ").split()))
        # audit row: masked recipient, SENT
        log = NotificationLog.objects.get(event=Events.PASSWORD_RESET, channel="sms")
        self.assertEqual(log.status, NotificationLog.Status.SENT)
        self.assertNotIn("+989127000001", log.recipient_masked)
        self.assertIn("*", log.recipient_masked)

    def test_template_mode_sends_code_as_token(self):
        with override_settings(SMS_TEMPLATE_PASSWORD_RESET="cusin_reset"):
            with self.captureOnCommitCallbacks(execute=True):
                self.request_reset(self.user.phone)
        sent = self.fake.sent[-1]
        self.assertEqual(sent["template"], "cusin_reset")
        self.assertTrue(sent["tokens"]["token"].isdigit())
        self.assertEqual(len(sent["tokens"]["token"]), 6)

    def test_confirm_with_code_changes_the_password_and_consumes_the_code(self):
        code = self.issue_code_for(self.user)

        response = self.confirm_with_code(self.user.phone, code)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-passw0rd!"))
        self.assertFalse(self.user.check_password("old-passw0rd!"))
        row = PhoneResetCode.objects.get(user=self.user)
        self.assertIsNotNone(row.consumed_at)
        # ...and the customer can actually log in with it now.
        self.assertTrue(self.client.login(username="+989127000001", password="brand-new-passw0rd!"))

    def test_code_is_single_use(self):
        code = self.issue_code_for(self.user)
        first = self.confirm_with_code(self.user.phone, code, password="first-new-pw123!")
        self.assertEqual(first.status_code, http_status.HTTP_200_OK)

        second = self.confirm_with_code(self.user.phone, code, password="second-new-pw123!")
        self.assertEqual(second.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("first-new-pw123!"))

    def test_expired_code_is_rejected(self):
        code = self.issue_code_for(self.user)
        PhoneResetCode.objects.filter(user=self.user).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = self.confirm_with_code(self.user.phone, code)

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-passw0rd!"))

    def test_wrong_code_is_rejected_with_the_same_generic_error(self):
        code = self.issue_code_for(self.user)
        wrong = "000000" if code != "000000" else "000001"

        wrong_response = self.confirm_with_code(self.user.phone, wrong)
        unknown_response = self.confirm_with_code("+989127999999", code)

        self.assertEqual(wrong_response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unknown_response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # Same generic message for wrong code and unknown phone: no oracle.
        self.assertEqual(wrong_response.data, unknown_response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-passw0rd!"))

    def test_reissuing_invalidates_the_previous_code(self):
        first_code = self.issue_code_for(self.user)
        second_code = self.issue_code_for(self.user)
        self.assertNotEqual(PhoneResetCode.objects.filter(user=self.user).count(), 0)
        self.assertEqual(PhoneResetCode.objects.filter(user=self.user).count(), 1,
                         "only ONE open code may exist per user")

        old = self.confirm_with_code(self.user.phone, first_code)
        self.assertEqual(old.status_code, http_status.HTTP_400_BAD_REQUEST)

        new = self.confirm_with_code(self.user.phone, second_code)
        self.assertEqual(new.status_code, http_status.HTTP_200_OK)

    def test_request_for_unknown_phone_is_indistinguishable(self):
        known = make_user(phone="+989127000002")
        with self.captureOnCommitCallbacks(execute=True):
            known_response = self.request_reset(known.phone)
            unknown_response = self.request_reset("+989127000099")
        self.assertEqual(known_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(unknown_response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(known_response.data, unknown_response.data)

    def test_request_endpoint_is_rate_limited(self):
        user = make_user(phone="+989127000003")
        responses = []
        with self.captureOnCommitCallbacks(execute=True):
            for _ in range(6):  # password_reset scope is 5/hour
                responses.append(self.request_reset(user.phone))
        self.assertEqual(
            [r.status_code for r in responses],
            [http_status.HTTP_200_OK] * 5 + [http_status.HTTP_429_TOO_MANY_REQUESTS],
        )

    def test_confirm_requires_one_complete_credential_pair(self):
        response = self.client.post(
            self.confirm_url,
            {"phone": self.user.phone, "new_password": "x-passw0rd-123!",
             "new_password_confirm": "x-passw0rd-123!"},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_code_must_satisfy_password_policy(self):
        code = self.issue_code_for(self.user)
        response = self.confirm_with_code(self.user.phone, code, password="123")
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-passw0rd!"))

    def test_provider_failure_is_contained_and_logged(self):
        self.fake.error = provider_error("kavenegar down")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.request_reset(self.user.phone)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)  # generic, unbroken
        log = NotificationLog.objects.get(event=Events.PASSWORD_RESET, channel="sms")
        self.assertEqual(log.status, NotificationLog.Status.FAILED)
        self.assertIn("kavenegar down", log.error)
        # The code row exists but never reached the customer; requesting
        # again issues a fresh one (the old is deleted) -- recoverable.
        self.assertTrue(PhoneResetCode.objects.filter(user=self.user).exists())

    def test_sms_disabled_records_skipped_and_stays_generic(self):
        with override_settings(SMS_ENABLED=False):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.request_reset(self.user.phone)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(self.fake.sent, [])
        log = NotificationLog.objects.get(event=Events.PASSWORD_RESET, channel="sms")
        self.assertEqual(log.status, NotificationLog.Status.SKIPPED)
        self.assertIn("SMS_ENABLED", log.error)


class EmailAccountResetFlowTests(PasswordResetSMSTestBase):
    def setUp(self):
        super().setUp()
        self.fake = install_fake_provider(self)

    def test_email_account_still_gets_the_link_and_no_sms(self):
        user = make_user(phone="+989127000010", email="mixed@example.com")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.request_reset(user.email)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(self.fake.sent, [], "an account with an email uses the link flow")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset-password/confirm", mail.outbox[0].body)
        log = NotificationLog.objects.get(event=Events.PASSWORD_RESET, channel="email")
        self.assertEqual(log.status, NotificationLog.Status.SENT)
        self.assertIn("m***@example.com", log.recipient_masked)

    def test_identifier_can_be_the_phone_even_when_email_exists(self):
        """Looking the account up by phone must find the same user and
        use the email channel (email wins when present)."""
        user = make_user(phone="+989127000011", email="mixed2@example.com")
        with self.captureOnCommitCallbacks(execute=True):
            self.request_reset(user.phone)
        self.assertEqual(self.fake.sent, [])
        self.assertEqual(len(mail.outbox), 1)
