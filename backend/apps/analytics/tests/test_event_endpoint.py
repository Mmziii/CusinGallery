"""Task 1: the batched storefront event endpoint.

Covers validation, rate limiting, bot filtering, the privacy guarantees
(no IP / no user agent stored) and the anonymous session key.
"""
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.testing import CacheIsolationMixin
from apps.products.models import Product

from ..models import Event
from ..tracking import SESSION_COOKIE, SESSION_HEADER
from .helpers import make_customer, make_product

ENDPOINT = "/api/v1/analytics/events/"
SESSION = "anon-session-123456"


@override_settings(ANALYTICS_RATE_LIMIT_PER_MINUTE=1000)
class EventEndpointTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.product = make_product(name="کتری لعابی")

    def _post(self, payload, **extra):
        return self.client.post(
            ENDPOINT, data=json.dumps(payload), content_type="application/json", **extra
        )

    def test_a_batch_of_events_is_stored_with_the_anonymous_session(self):
        response = self._post({
            "session_key": SESSION,
            "events": [
                {"type": "product_view", "product_id": self.product.pk},
                {"type": "search", "query": "کتری", "results": 3},
                {"type": "checkout_started"},
            ],
        })
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["accepted"], 3)
        rows = list(Event.objects.order_by("pk"))
        self.assertEqual(
            [row.event_type for row in rows],
            ["product_view", "search", "checkout_started"],
        )
        self.assertEqual(rows[0].product_id, self.product.pk)
        self.assertEqual(rows[1].search_query, "کتری")
        self.assertEqual(rows[1].search_results, 3)
        self.assertEqual({row.session_key for row in rows}, {SESSION})

    def test_unknown_types_and_malformed_entries_are_skipped_not_rejected(self):
        response = self._post({
            "session_key": SESSION,
            "events": [
                "not-a-dict",
                {"type": "made_up_event"},
                {"type": "product_view", "product_id": "not-an-int"},
                {"type": "search", "query": ""},  # a search needs a query
                {"type": "add_to_cart", "product_id": 999999},
                {"type": "wishlist_add", "product_id": self.product.pk},
            ],
        })
        self.assertEqual(response.status_code, 202)
        # product_view (unknown id), add_to_cart (unknown id) and
        # wishlist_add are stored; the bogus type and the empty search
        # are skipped. None of this is an error the UI could ever see.
        self.assertEqual(response.json()["accepted"], 3)
        self.assertEqual(
            sorted(Event.objects.values_list("event_type", flat=True)),
            ["add_to_cart", "product_view", "wishlist_add"],
        )

    def test_a_missing_event_list_is_a_clear_400(self):
        response = self._post({"session_key": SESSION})
        self.assertEqual(response.status_code, 400)

    def test_no_session_key_means_nothing_is_stored_and_no_error(self):
        response = self._post({
            "events": [{"type": "product_view", "product_id": self.product.pk}],
        })
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["accepted"], 0)
        self.assertFalse(Event.objects.exists())

    def test_the_session_key_can_arrive_in_a_header(self):
        self.client.post(
            ENDPOINT,
            data=json.dumps({"events": [{"type": "product_view", "product_id": self.product.pk}]}),
            content_type="application/json",
            HTTP_X_CUSIN_SESSION="header-session-abcdef",
        )
        self.assertEqual(
            Event.objects.get().session_key, "header-session-abcdef",
        )

    def test_the_session_key_can_arrive_in_the_cookie(self):
        self.client.cookies[SESSION_COOKIE] = "cookie-session-abcdef"
        self._post({
            "events": [{"type": "product_view", "product_id": self.product.pk}],
        })
        self.assertEqual(Event.objects.get().session_key, "cookie-session-abcdef")

    def test_bots_are_ignored(self):
        response = self._post(
            {"session_key": SESSION, "events": [{"type": "product_view"}]},
            HTTP_USER_AGENT="Mozilla/5.0 (compatible; Googlebot/2.1)",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["accepted"], 0)
        self.assertFalse(Event.objects.exists())

    def test_a_logged_in_customer_is_attached_by_the_server(self):
        customer = make_customer()
        self.client.force_login(customer)
        self._post({
            "session_key": SESSION,
            "events": [{"type": "product_view", "product_id": self.product.pk}],
        })
        self.assertEqual(Event.objects.get().user_id, customer.pk)

    def test_no_ip_and_no_user_agent_is_stored_anywhere(self):
        """Privacy guarantee, asserted against an actual request."""
        self._post(
            {"session_key": SESSION, "events": [{"type": "product_view"}]},
            REMOTE_ADDR="203.0.113.9",
            HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0",
        )
        row = Event.objects.get()
        field_names = {field.name for field in Event._meta.get_fields()}
        self.assertNotIn("ip", field_names)
        self.assertNotIn("ip_address", field_names)
        self.assertNotIn("user_agent", field_names)
        # And no value smuggled into the free-text columns either.
        values = " ".join(
            str(getattr(row, name) or "")
            for name in ("session_key", "search_query", "province", "city")
        )
        self.assertNotIn("203.0.113.9", values)
        self.assertNotIn("Firefox", values)

    def test_a_batch_is_capped(self):
        with override_settings(ANALYTICS_MAX_BATCH=2):
            response = self._post({
                "session_key": SESSION,
                "events": [{"type": "product_view", "product_id": self.product.pk}] * 5,
            })
        self.assertEqual(response.json()["accepted"], 2)

    def test_product_ids_point_at_real_products_only(self):
        self._post({
            "session_key": SESSION,
            "events": [{"type": "product_view", "product_id": 424242}],
        })
        self.assertTrue(Event.objects.filter(product__isnull=True).exists())


@override_settings(ANALYTICS_RATE_LIMIT_PER_MINUTE=3)
class EventRateLimitTests(CacheIsolationMixin, TestCase):
    def test_too_many_batches_are_silently_ignored_and_store_nothing(self):
        payload = {
            "session_key": "rate-limit-session-1",
            "events": [{"type": "product_view"}],
        }
        for _ in range(3):
            response = self.client.post(
                ENDPOINT, data=json.dumps(payload), content_type="application/json",
            )
            self.assertEqual(response.status_code, 202)
        response = self.client.post(
            ENDPOINT, data=json.dumps(payload), content_type="application/json",
        )
        # Fire-and-forget: same 202 as always, just nothing stored.
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"accepted": 0, "ignored": "rate-limited"})
        self.assertEqual(Event.objects.count(), 3)

    def test_one_sessions_limit_does_not_block_another(self):
        for key in ("session-aaaaaaaa", "session-bbbbbbbb"):
            payload = {"session_key": key, "events": [{"type": "product_view"}]}
            for _ in range(3):
                response = self.client.post(
                    ENDPOINT, data=json.dumps(payload), content_type="application/json",
                )
                self.assertEqual(response.status_code, 202)
        response = self.client.post(
            ENDPOINT,
            data=json.dumps({"session_key": "session-cccccccc", "events": [{"type": "product_view"}]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
