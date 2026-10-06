"""
Tests for the test infrastructure itself (apps/core/testing.py).

These exist because the cache-isolation mechanism caused a REAL
full-suite failure: test classes overriding setUp() without calling
super().setUp() silently skipped the cache clear, DRF throttle counters
accumulated across classes, and a checkout test got HTTP 429 instead of
the expected 400. The fix moved the clear into _pre_setup(); these
tests lock that property in.
"""
import unittest

from django.core.cache import cache
from django.test import SimpleTestCase

from .testing import CacheIsolationMixin


class CacheIsolationMechanismTests(SimpleTestCase):
    def test_pre_setup_clears_the_cache(self):
        cache.set("sentinel", 42)

        class Harness(CacheIsolationMixin, SimpleTestCase):
            def test_placeholder(self):  # never executed; harness only
                pass

        harness = Harness("test_placeholder")
        harness._pre_setup()
        self.assertIsNone(cache.get("sentinel"))

    def test_pre_setup_works_when_django_calls_it_on_the_class(self):
        """
        Django 5.2's TransactionTestCase.setUpClass() calls `cls._pre_setup()`
        (the hook became a classmethod). An instance-method override here
        made both concurrency test classes fail in setUpClass with
        "missing 1 required positional argument: 'self'"; this asserts the
        class-level call path still clears the cache.
        """

        class Harness(CacheIsolationMixin, SimpleTestCase):
            pass

        cache.set("sentinel", 42)
        Harness._pre_setup()
        self.assertIsNone(cache.get("sentinel"))

    def test_clear_survives_subclass_setup_that_skips_super(self):
        """
        The exact bypass that caused the 429: a subclass defines setUp()
        and never calls super().setUp(). Run two tests through the real
        unittest lifecycle -- the first pollutes the cache, the second
        must start clean.
        """
        observed = []

        class BypassingSetUp(CacheIsolationMixin, SimpleTestCase):
            def setUp(self):
                # Deliberately NO super().setUp() call.
                pass

            def test_a_pollutes_the_cache(self):
                cache.set("throttle-counter-sentinel", 99)

            def test_b_must_start_with_a_clean_cache(self):
                observed.append(cache.get("throttle-counter-sentinel"))

        suite = unittest.TestSuite(
            [
                BypassingSetUp("test_a_pollutes_the_cache"),
                BypassingSetUp("test_b_must_start_with_a_clean_cache"),
            ]
        )
        result = unittest.TestResult()
        suite.run(result)

        self.assertEqual(result.testsRun, 2)
        self.assertEqual([f for f in (result.failures, result.errors)], [[], []])
        self.assertEqual(observed, [None])
