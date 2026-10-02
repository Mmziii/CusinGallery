"""
Shared test infrastructure.

CacheIsolated* test cases clear Django's cache before every test. DRF's
throttling stores its hit counters in the cache, and with the default
LocMem backend that cache lives for the ENTIRE test run -- so without a
clear, one test's requests count against the next test's quota and
throttled endpoints (register, login, checkout, payment initiation...)
start failing with HTTP 429 deep into the suite, depending on execution
order. Clearing per test makes throttled-endpoint tests deterministic.

Why the clear lives in _pre_setup() and NOT in setUp():
Django calls SimpleTestCase._pre_setup() before setUp() on every test,
and a subclass that defines its own setUp() without calling
super().setUp() -- which several test classes in this repo legitimately
do -- can silently skip an setUp()-based clear. _pre_setup() is only
skipped if a subclass overrides _pre_setup() itself and forgets super,
which is far rarer and auditable. This was a real bug: a full-suite run
saw checkout throttle counters accumulate across classes and return
HTTP 429 instead of the expected 400.

This does NOT weaken the production throttles in any way: the rates in
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] are untouched -- tests simply
each get their own fresh counter window, which is the same isolation
Django gives them for the database via transaction rollback.
"""
from django.core.cache import cache
from rest_framework.test import APITestCase, APITransactionTestCase


class CacheIsolationMixin:
    def _pre_setup(self):
        super()._pre_setup()
        cache.clear()
        # Belt and braces: also clear after the test body. Some flows
        # (thread-based TransactionTestCase tests) populate the cache
        # during a test in ways that must not leak into the next one
        # even if the next test's own _pre_setup were ever bypassed.
        self.addCleanup(cache.clear)


class CacheIsolatedAPITestCase(CacheIsolationMixin, APITestCase):
    """APITestCase with a clean cache (and thus clean throttle counters)
    at the start of every test."""


class CacheIsolatedAPITransactionTestCase(CacheIsolationMixin, APITransactionTestCase):
    """Same isolation for transaction-style API tests (real threads need
    these; see e.g. apps/payments/tests/test_api.py)."""
