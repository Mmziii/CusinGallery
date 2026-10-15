"""
Payment status wording and the abandoned-order default view.

* «در انتظار پرداخت» suggested the SHOP was waiting for money, when the
  value actually means the customer's attempt is in flight at the gateway
  -- it is now «در حال پرداخت در درگاه». «پرداخت نشده» stays as it was.
* The order list and the order page show what the CUSTOMER did on the
  last attempt («موفق» / «ناموفق» / «لغو توسط مشتری») and when.
* Abandoned unpaid orders are hidden from the DEFAULT work queue (they
  are noise), but never unreachable: they have a tab and a "show all"
  link, and any explicit filter brings them back.
"""
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.adminui.tests.helpers import PLAIN_STATIC, make_order, make_superuser
from apps.orders.admin import LAST_ATTEMPT_PHRASES, abandoned_unpaid_q
from apps.orders.models import Order
from apps.payments.models import Payment

S = Order.Status
PS = Order.PaymentStatus


@override_settings(**PLAIN_STATIC)
class PaymentStatusLabelTests(TestCase):
    def test_pending_means_the_attempt_is_in_flight_at_the_gateway(self):
        self.assertEqual(Order.PaymentStatus("pending").label, "در حال پرداخت در درگاه")

    def test_unpaid_keeps_its_label(self):
        self.assertEqual(Order.PaymentStatus("unpaid").label, "پرداخت نشده")

    def test_the_whole_vocabulary_is_persian_and_distinct(self):
        labels = {value: label for value, label in Order.PaymentStatus.choices}
        self.assertEqual(len(set(labels.values())), len(labels), labels)
        self.assertNotIn("pending", " ".join(labels.values()))

    def test_owner_facing_attempt_phrases(self):
        self.assertEqual(LAST_ATTEMPT_PHRASES[Payment.Status.SUCCESS], "موفق")
        self.assertEqual(LAST_ATTEMPT_PHRASES[Payment.Status.FAILED], "ناموفق")
        self.assertEqual(LAST_ATTEMPT_PHRASES[Payment.Status.CANCELLED], "لغو توسط مشتری")


@override_settings(**PLAIN_STATIC)
class LastAttemptDisplayTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="attemptowner", phone="+989000041001")
        self.client.force_login(self.admin)
        self.order = make_order(status=S.PENDING, payment_status=PS.PENDING)

    def _attempt(self, status, **extra):
        return Payment.objects.create(
            order=self.order,
            amount=self.order.total,
            status=status,
            gateway="mock",
            **extra,
        )

    def test_the_list_shows_the_last_attempt_and_its_time(self):
        self._attempt(Payment.Status.FAILED, failure_reason="موجودی کافی نیست")
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        self.assertIn("ناموفق", html)
        self.assertIn("cusin-attempt", html)
        # A Jalali time next to it, not a Gregorian one.
        self.assertNotIn("2026-", html.split("cusin-attempt")[1][:200])

    def test_cancelled_reads_as_the_customer_cancelling(self):
        self._attempt(Payment.Status.CANCELLED)
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        self.assertIn("لغو توسط مشتری", html)

    def test_success_reads_as_successful(self):
        self._attempt(Payment.Status.SUCCESS)
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        self.assertIn("موفق", html)

    def test_the_newest_attempt_wins(self):
        self._attempt(Payment.Status.FAILED)
        self._attempt(Payment.Status.SUCCESS)
        context = self._change_page()
        self.assertEqual(context["summary_last_attempt"]["label"], "موفق")

    def test_the_change_page_shows_the_attempt_with_its_reason(self):
        self._attempt(Payment.Status.FAILED, failure_reason="موجودی کافی نیست")
        context = self._change_page()
        attempt = context["summary_last_attempt"]
        self.assertEqual(attempt["label"], "ناموفق")
        self.assertEqual(attempt["reason"], "موجودی کافی نیست")
        self.assertIsNotNone(attempt["at"])

    def test_an_order_with_no_attempt_shows_a_dash_not_a_crash(self):
        context = self._change_page()
        self.assertIsNone(context["summary_last_attempt"])
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        self.assertIn("cusin-muted", html)

    def test_the_changelist_uses_one_prefetch_not_one_query_per_row(self):
        """The prefetch set up in get_queryset must actually be used."""
        for _ in range(5):
            self._attempt(Payment.Status.FAILED)
        for _ in range(5):
            make_order(status=S.PENDING, payment_status=PS.PENDING)

        with CaptureQueriesContext(connection) as baseline:
            self.client.get(reverse("admin:orders_order_changelist"))
        baseline_count = len(baseline.captured_queries)

        # 40 more orders on the page: the payment lookups are prefetched,
        # so the query count must stay flat instead of growing per row.
        for _ in range(40):
            order = make_order(status=S.PENDING, payment_status=PS.PENDING)
            Payment.objects.create(
                order=order, amount=order.total, status=Payment.Status.FAILED, gateway="mock",
            )
        with CaptureQueriesContext(connection) as grown:
            self.client.get(reverse("admin:orders_order_changelist"))
        self.assertLessEqual(
            len(grown.captured_queries) - baseline_count, 2,
            "the last-attempt column is fanning out queries",
        )

    def _change_page(self):
        return self.client.get(
            reverse("admin:orders_order_change", args=[self.order.pk])
        ).context


@override_settings(**PLAIN_STATIC)
class AbandonedOrderHidingTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="abandonowner", phone="+989000042001")
        self.client.force_login(self.admin)
        self.url = reverse("admin:orders_order_changelist")
        self.fresh_unpaid = make_order(status=S.PENDING, payment_status=PS.UNPAID)
        self.stale_unpaid = make_order(status=S.PENDING, payment_status=PS.UNPAID)
        Order.objects.filter(pk=self.stale_unpaid.pk).update(
            created_at=timezone.now() - timedelta(hours=48)
        )
        self.paid = make_order(status=S.PENDING, payment_status=PS.PAID)

    def test_the_abandoned_predicate_is_age_aware(self):
        ids = set(Order.objects.filter(abandoned_unpaid_q()).values_list("pk", flat=True))
        self.assertEqual(ids, {self.stale_unpaid.pk})

    def test_the_default_list_hides_abandoned_orders(self):
        response = self.client.get(self.url)
        ids = {row.pk for row in response.context["cl"].queryset}
        self.assertIn(self.fresh_unpaid.pk, ids)
        self.assertIn(self.paid.pk, ids)
        self.assertNotIn(self.stale_unpaid.pk, ids)

    def test_hiding_is_announced_with_a_link(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["hidden_abandoned_count"], 1)
        html = response.content.decode()
        self.assertIn("cusin-hidden-note", html)
        self.assertIn("all=1", html)
        self.assertIn("سفارش‌های رهاشده", html)

    def test_the_abandoned_tab_finds_them(self):
        response = self.client.get(self.url + "?queue=abandoned")
        ids = {row.pk for row in response.context["cl"].queryset}
        self.assertEqual(ids, {self.stale_unpaid.pk})

    def test_show_all_brings_them_back(self):
        response = self.client.get(self.url + "?all=1")
        ids = {row.pk for row in response.context["cl"].queryset}
        self.assertEqual(ids, {self.fresh_unpaid.pk, self.stale_unpaid.pk, self.paid.pk})

    def test_any_explicit_filter_brings_them_back(self):
        for query in ("?payment_status__exact=unpaid", "?status__exact=pending", "?q=CG"):
            with self.subTest(query=query):
                response = self.client.get(self.url + query)
                ids = {row.pk for row in response.context["cl"].queryset}
                self.assertIn(self.stale_unpaid.pk, ids, query)

    def test_tab_counts_still_include_hidden_orders(self):
        """A hidden count is how work gets lost -- tabs must stay honest."""
        response = self.client.get(self.url)
        tabs = {tab["key"]: tab for tab in response.context["queue_tabs"]}
        self.assertEqual(tabs["all"]["count"], 3)
        self.assertEqual(tabs["abandoned"]["count"], 1)
        self.assertEqual(tabs["awaiting_payment"]["count"], 2)

    def test_a_paid_order_is_never_hidden_however_old(self):
        Order.objects.filter(pk=self.paid.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        response = self.client.get(self.url)
        ids = {row.pk for row in response.context["cl"].queryset}
        self.assertIn(self.paid.pk, ids)
