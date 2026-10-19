"""Abuse resistance of the batched tracking endpoint.

The browser chooses ``session_key``, so a limit keyed only on it is not a
limit at all: rotate the key and get unlimited batches. These tests pin the
independent counters that close that hole -- per hashed address, per hour
of NEW session keys, and the endpoint-wide cap -- and the privacy rule that
the address only ever exists inside a cache key.
"""
import json

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.testing import CacheIsolationMixin

from ..models import Event
from ..ratelimit import fingerprint_ip
from .helpers import make_product

ENDPOINT = "/api/v1/analytics/events/"
CLIENT = "198.51.100.7"
PROXY = "172.18.0.5"


def _payload(session_key):
    return {"session_key": session_key, "events": [{"type": "product_view"}]}


class RateLimitTestBase(CacheIsolationMixin, TestCase):
    def setUp(self):
        make_product(name="کتری لعابی")

    def post(self, session_key, **extra):
        return self.client.post(
            ENDPOINT,
            data=json.dumps(_payload(session_key)),
            content_type="application/json",
            **extra,
        )


@override_settings(
    ANALYTICS_RATE_LIMIT_PER_MINUTE=1000,
    ANALYTICS_IP_RATE_LIMIT_PER_MINUTE=5,
    ANALYTICS_SESSION_KEYS_PER_IP_PER_HOUR=1000,
    ANALYTICS_GLOBAL_RATE_LIMIT_PER_MINUTE=1000,
)
class SessionKeyRotationTests(RateLimitTestBase):
    """The reported bypass: 70 batches, 70 different keys, one address."""

    def test_rotating_the_session_key_does_not_buy_extra_batches(self):
        responses = [self.post(f"rotated-key-{index:04d}") for index in range(70)]

        self.assertEqual({response.status_code for response in responses}, {202})
        self.assertEqual(Event.objects.count(), 5)
        throttled = [response.json() for response in responses[5:]]
        self.assertTrue(throttled)
        for body in throttled:
            self.assertEqual(body, {"accepted": 0, "ignored": "rate-limited"})

    def test_the_limit_follows_the_address_not_the_header_chain(self):
        """Rotating every key AND every value in the payload changes nothing."""
        for index in range(5):
            self.assertNotEqual(
                self.post(f"same-client-key-{index}", REMOTE_ADDR=CLIENT).json()["accepted"],
                0,
            )
        body = self.post("another-key-entirely", REMOTE_ADDR=CLIENT).json()
        self.assertEqual(body, {"accepted": 0, "ignored": "rate-limited"})
        self.assertEqual(Event.objects.count(), 5)


@override_settings(
    ANALYTICS_RATE_LIMIT_PER_MINUTE=1000,
    ANALYTICS_IP_RATE_LIMIT_PER_MINUTE=1000,
    ANALYTICS_SESSION_KEYS_PER_IP_PER_HOUR=3,
    ANALYTICS_GLOBAL_RATE_LIMIT_PER_MINUTE=1000,
)
class NewSessionKeyBudgetTests(RateLimitTestBase):
    def test_one_address_can_only_mint_so_many_new_keys_per_hour(self):
        for index in range(10):
            response = self.post(f"fresh-session-{index:04d}")
            self.assertEqual(response.status_code, 202)

        self.assertEqual(Event.objects.count(), 3)
        self.assertEqual(
            Event.objects.values_list("session_key", flat=True).distinct().count(), 3,
        )

    def test_returning_keys_do_not_consume_the_budget(self):
        for index in range(3):
            self.assertEqual(self.post(f"known-session-{index:04d}").json()["accepted"], 1)
        # The cap is on NEW keys; re-sending a known one still works.
        body = self.post("known-session-0000").json()
        self.assertEqual(body["accepted"], 1)
        self.assertEqual(Event.objects.count(), 4)


@override_settings(
    ANALYTICS_RATE_LIMIT_PER_MINUTE=1000,
    ANALYTICS_IP_RATE_LIMIT_PER_MINUTE=1000,
    ANALYTICS_SESSION_KEYS_PER_IP_PER_HOUR=1000,
    ANALYTICS_GLOBAL_RATE_LIMIT_PER_MINUTE=2,
)
class GlobalSafetyCapTests(RateLimitTestBase):
    def test_the_endpoint_has_a_ceiling_even_across_many_addresses(self):
        addresses = ["203.0.113.11", "203.0.113.12", "203.0.113.13", "203.0.113.14"]
        responses = [
            self.post(f"distributed-key-{index:04d}", REMOTE_ADDR=address)
            for index, address in enumerate(addresses)
        ]
        self.assertEqual(Event.objects.count(), 2)
        for body in (response.json() for response in responses[2:]):
            self.assertEqual(body, {"accepted": 0, "ignored": "rate-limited"})


@override_settings(
    ANALYTICS_RATE_LIMIT_PER_MINUTE=1000,
    ANALYTICS_IP_RATE_LIMIT_PER_MINUTE=2,
    ANALYTICS_SESSION_KEYS_PER_IP_PER_HOUR=1000,
    ANALYTICS_GLOBAL_RATE_LIMIT_PER_MINUTE=1000,
)
class ForwardedAddressTests(RateLimitTestBase):
    """Only a declared trusted proxy is allowed to name the client."""

    @override_settings(ANALYTICS_TRUSTED_PROXY_COUNT=0)
    def test_forwarded_for_is_ignored_without_a_trusted_proxy(self):
        # Spoofing X-Forwarded-For must not reset the per-address counter:
        # with no declared proxy the socket peer is the identity.
        values = ["192.0.2.1", "192.0.2.2", "192.0.2.3"]
        for index, forwarded in enumerate(values):
            response = self.post(
                f"spoofed-key-{index:04d}",
                REMOTE_ADDR=CLIENT,
                HTTP_X_FORWARDED_FOR=forwarded,
            )
            if index < 2:
                self.assertEqual(response.json()["accepted"], 1)
        self.assertEqual(response.json(), {"accepted": 0, "ignored": "rate-limited"})
        self.assertEqual(Event.objects.count(), 2)

    @override_settings(ANALYTICS_TRUSTED_PROXY_COUNT=1)
    def test_behind_one_proxy_the_last_hop_is_the_client(self):
        for index, spoofed in enumerate(["1.1.1.1", "2.2.2.2", "3.3.3.3"]):
            response = self.post(
                f"proxied-key-{index:04d}",
                REMOTE_ADDR=PROXY,
                HTTP_X_FORWARDED_FOR=f"{spoofed}, {CLIENT}",
            )
            self.assertEqual(response.status_code, 202)
        # Same real client every time -> same budget, despite the spoofed
        # left-hand entries differing on every request.
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(response.json(), {"accepted": 0, "ignored": "rate-limited"})

    @override_settings(ANALYTICS_TRUSTED_PROXY_COUNT=1)
    def test_different_clients_behind_the_same_proxy_keep_separate_budgets(self):
        for index, client in enumerate(["198.51.100.7", "198.51.100.8", "198.51.100.9"]):
            body = self.post(
                f"behind-proxy-{index:04d}",
                REMOTE_ADDR=PROXY,
                HTTP_X_FORWARDED_FOR=client,
            ).json()
            self.assertEqual(body["accepted"], 1)
        self.assertEqual(Event.objects.count(), 3)


class AddressIsNeverStoredTests(RateLimitTestBase):
    def test_the_address_is_only_a_salted_cache_key(self):
        digest = fingerprint_ip(CLIENT)
        self.assertEqual(len(digest), 64)
        self.assertNotIn(CLIENT, digest)
        self.assertNotEqual(digest, fingerprint_ip("198.51.100.8"))

    def test_no_table_column_or_row_ever_holds_the_address(self):
        self.post("privacy-session-0001", REMOTE_ADDR=CLIENT)
        field_names = {field.name for field in Event._meta.get_fields()}
        self.assertFalse(field_names & {"ip", "ip_address", "client_ip", "remote_addr"})
        row = Event.objects.get()
        values = " ".join(
            str(getattr(row, name) or "")
            for name in ("session_key", "search_query", "province", "city")
        )
        self.assertNotIn(CLIENT, values)

    def test_the_cache_holds_the_address_hashed_never_in_clear(self):
        self.post("privacy-session-0002", REMOTE_ADDR=CLIENT)
        if not hasattr(cache, "_cache"):
            self.skipTest("only the LocMem test backend exposes its key map")
        keys = list(cache._cache.keys())
        self.assertTrue(any("analytics:rl:ip:" in str(key) for key in keys))
        self.assertFalse(any(CLIENT in str(key) for key in keys))
        self.assertTrue(any(fingerprint_ip(CLIENT) in str(key) for key in keys))
