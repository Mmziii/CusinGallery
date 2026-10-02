"""
Shared test infrastructure.

CacheIsolated* test cases clear Django's cache before every test. DRF's
throttling stores its hit counters in the cache, and with the default
LocMem backend that cache lives for the ENTIRE test run -- so without a
clear, one test's requests count against the next test's quota and
throttled endpoints (register, login, checkout, payment initiation...)
start failing with HTTP 429 deep into the suite, depending on execution
order. Clearing per test makes throttled-endpoint tests deterministic.

This does NOT weaken the production throttles in any way: the rates in
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] are untouched -- tests simply
each get their own fresh counter window, which is the same isolation
Django gives them for the database via transaction rollback.
"""
from django.core.cache import cache
from rest_framework.test import APITestCase, APITransactionTestCase


class CacheIsolationMixin:
    def setUp(self):
        super().setUp()
        cache.clear()


class CacheIsolatedAPITestCase(CacheIsolationMixin, APITestCase):
    """APITestCase with a clean cache (and thus clean throttle counters)
    at the start of every test."""


class CacheIsolatedAPITransactionTestCase(CacheIsolationMixin, APITransactionTestCase):
    """Same isolation for transaction-style API tests (real threads need
    these; see e.g. apps/payments/tests/test_api.py)."""
