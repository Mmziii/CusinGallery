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
from contextlib import contextmanager
from unittest import mock

from django.core.cache import cache
from rest_framework.test import APITestCase, APITransactionTestCase


@contextmanager
def frozen_clock(moment):
    """Run the block at `moment` on Django's clock.

    `django.utils.timezone.now` is patched PROCESS-WIDE rather than in one
    caller's module: auto_now/auto_now_add model fields read that same
    function, so faking only the module under test would leave every
    stored timestamp on the real wall clock. Any later comparison of such
    a row against the fake "now" then silently measures how much REAL time
    has passed since the row was written instead of the scenario the test
    describes.

    That is exactly how apps.notifications.tests.test_cart_reminders
    became a time bomb: its fixed 2026-10-05 clock was eventually behind
    NotificationLog.created_at (written with the real clock), so on
    2026-10-06 the "eight days later" run saw the first reminder as
    still inside the cooldown and stopped reminding. Patching the shared
    clock keeps the stored timestamps and the code's own comparisons on
    the same timeline, which is what makes a date-pinned test independent
    of the wall clock it happens to run on.
    """
    with mock.patch("django.utils.timezone.now", return_value=moment) as fake_now:
        yield fake_now


class CacheIsolationMixin:
    # NOTE the classmethod: Django 5.2 turned SimpleTestCase._pre_setup into
    # a classmethod and TransactionTestCase.setUpClass() now calls it on the
    # CLASS (`cls._pre_setup()`) for non-TestCase subclasses. An instance
    # method here made the two concurrency test classes die in setUpClass
    # with "missing 1 required positional argument: 'self'" the moment this
    # project moved off Django 5.0. A classmethod is called correctly on
    # both paths (class and instance), so the mixin works on 5.0 and 5.2.
    @classmethod
    def _pre_setup(cls):
        super()._pre_setup()
        cache.clear()

    def _post_teardown(self):
        # Belt and braces: also clear after the test body. Some flows
        # (thread-based TransactionTestCase tests) populate the cache
        # during a test in ways that must not leak into the next one
        # even if the next test's own _pre_setup were ever bypassed.
        # This replaces the old addCleanup(cache.clear): addCleanup needs
        # an INSTANCE, and on Django 5.2 the pre-setup hook can run before
        # any instance exists.
        try:
            super()._post_teardown()
        finally:
            cache.clear()


class CacheIsolatedAPITestCase(CacheIsolationMixin, APITestCase):
    """APITestCase with a clean cache (and thus clean throttle counters)
    at the start of every test."""


class CacheIsolatedAPITransactionTestCase(CacheIsolationMixin, APITransactionTestCase):
    """Same isolation for transaction-style API tests (real threads need
    these; see e.g. apps/payments/tests/test_api.py)."""


class ClockFrozenTestCaseMixin:
    """Freeze Django's clock for the WHOLE test (setUp included).

    Set `FROZEN_NOW` on the subclass. Freezing from setUp matters when the
    test logs in or builds session/CSRF state: Django signs a session's
    expiry into the cookie, so a session created at the real clock and then
    evaluated under a faked "now" can read as expired -- which is how
    apps.orders.tests.test_shipping's checkout test lost its login (HTTP
    403, no order) whenever the suite ran with a faked clock far from the
    fixed date. Entering the freeze before setUp keeps the session, the
    rows it writes and the assertions on ONE timeline.
    """

    FROZEN_NOW = None

    # _pre_setup (not setUp) for the same reason CacheIsolationMixin uses it:
    # a subclass that defines its own setUp() without calling super() -- which
    # several test classes here legitimately do -- would silently skip the
    # freeze, and the whole point is that the clock is pinned before ANY of
    # the test's own setup runs. It is a classmethod because Django 5.2 calls
    # it on the class for TransactionTestCase subclasses (see the note on
    # CacheIsolationMixin._pre_setup).
    @classmethod
    def _pre_setup(cls):
        super()._pre_setup()
        if cls.FROZEN_NOW is not None and not getattr(cls, "_clock_is_frozen", False):
            context = frozen_clock(cls.FROZEN_NOW)
            context.__enter__()
            cls._clock_is_frozen = True
            # Exited once, at class teardown: unittest's addClassCleanup works
            # without an instance, which the 5.2 class-level call path does
            # not have.
            cls.addClassCleanup(context.__exit__, None, None, None)
