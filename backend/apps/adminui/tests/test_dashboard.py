"""B1: dashboard aggregates -- exact numbers from fixtures, Asia/Tehran
day boundaries, ~60s caching with bounded queries, per-model permission
gating (cards hidden AND target URLs protected), and the action-card
links really resolving to working changelists.
"""
import datetime as dt
import pickle

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.testing import CacheIsolationMixin, frozen_clock
from apps.adminui.dashboard import CACHE_KEY, build_payload, get_dashboard

from .helpers import (
    PLAIN_STATIC,
    make_customer,
    make_order,
    make_product,
    make_staff,
    make_superuser,
)

User = get_user_model()
TEHRAN = dt.timezone(dt.timedelta(hours=3, minutes=30))

# Frozen "now": Saturday 2026-10-10 12:00 Tehran == 08:30 UTC.
# Tehran day windows therefore run 20:30 UTC -> 20:30 UTC.
FROZEN = dt.datetime(2026, 10, 10, 12, 0, tzinfo=TEHRAN)


def utc(*args):
    return dt.datetime(*args, tzinfo=dt.timezone.utc)


def tehran(*args):
    return dt.datetime(*args, tzinfo=TEHRAN)


def _set_created(order, moment):
    type(order).objects.filter(pk=order.pk).update(created_at=moment)


@override_settings(**PLAIN_STATIC)
class DashboardNumbersTests(CacheIsolationMixin, TestCase):
    """Exact KPI values from a hand-built fixture set."""

    maxDiff = None

    def setUp(self):
        self.admin = make_superuser(username="dashowner", phone="+989000003333")
        self.product_a = make_product(name="قاشق چوبی", price=100000)
        self.product_b = make_product(name="کتری لعابی", price=50000)

    def _fixture_orders(self):
        from apps.orders.models import Order

        # today (Tehran 2026-10-10), paid, confirmed -- 200,000
        o1 = make_order(product=self.product_a, total=200000, subtotal=200000,
                        item={"unit_price": 100000, "quantity": 2,
                              "total_price": 200000})
        _set_created(o1, utc(2026, 10, 10, 5, 30))     # 09:00 Tehran today

        # today, paid but CANCELLED -- gross yes, net no
        o2 = make_order(product=self.product_b, total=100000, subtotal=100000,
                        status=Order.Status.CANCELLED,
                        item={"unit_price": 50000, "quantity": 2,
                              "total_price": 100000})
        _set_created(o2, utc(2026, 10, 10, 6, 30))     # 10:00 Tehran today

        # yesterday 23:59 Tehran (UTC 20:29) -- NOT today, still this week
        o3 = make_order(product=self.product_a, total=50000, subtotal=50000,
                        item={"unit_price": 100000, "quantity": 1,
                              "total_price": 50000})
        _set_created(o3, utc(2026, 10, 9, 20, 29))

        # today 00:00 Tehran exactly (UTC 20:30) -- boundary: counts as today
        o4 = make_order(product=self.product_a, total=70000, subtotal=70000,
                        payment_status=Order.PaymentStatus.UNPAID)
        _set_created(o4, utc(2026, 10, 9, 20, 30))

        # previous week window (8 days ago), paid -- 400,000
        o5 = make_order(product=self.product_b, total=400000, subtotal=400000)
        _set_created(o5, utc(2026, 10, 2, 8, 0))

        # ~40 days ago: only visible to the 30-day "previous" window
        o6 = make_order(product=self.product_a, total=999, subtotal=999)
        _set_created(o6, utc(2026, 8, 31, 8, 0))
        return [o1, o2, o3, o4, o5, o6]

    def _fixture_customers(self):
        c1 = make_customer()   # joined today
        User.objects.filter(pk=c1.pk).update(date_joined=utc(2026, 10, 10, 4, 0))
        c2 = make_customer()   # joined 3 days ago -> this week, not today
        User.objects.filter(pk=c2.pk).update(date_joined=utc(2026, 10, 7, 4, 0))
        c3 = make_customer()   # joined 9 days ago -> previous week window
        User.objects.filter(pk=c3.pk).update(date_joined=utc(2026, 10, 1, 4, 0))
        staff = make_staff(username="+989007778899", phone="+989007778899")
        User.objects.filter(pk=staff.pk).update(date_joined=utc(2026, 10, 10, 4, 0))
        # users auto-created by make_order() joined "now" (frozen today);
        # push them out of every window so new_customers stays exact
        User.objects.filter(is_staff=False).exclude(
            pk__in=[c1.pk, c2.pk, c3.pk]
        ).update(date_joined=utc(2026, 8, 1, 4, 0))
        return [c1, c2, c3, staff]

    def test_kpi_numbers_exact(self):
        with frozen_clock(FROZEN):
            self._fixture_orders()
            self._fixture_customers()
            payload = build_payload(14)

            today = payload["kpis"]["today"]["current"]
            self.assertEqual(today["orders"], 3)               # o1, o2, o4
            self.assertEqual(today["gross"], 300000)           # o1 + o2 (paid)
            self.assertEqual(today["cancelled_returned"], 100000)
            self.assertEqual(today["net"], 200000)
            self.assertEqual(today["aov"], 150000)             # 300000 / 2 paid
            self.assertEqual(today["new_customers"], 1)        # c1 only

            week = payload["kpis"]["week"]["current"]
            self.assertEqual(week["orders"], 4)                # o1..o4
            self.assertEqual(week["gross"], 350000)            # o1+o2+o3
            self.assertEqual(week["cancelled_returned"], 100000)
            self.assertEqual(week["net"], 250000)
            self.assertEqual(week["aov"], 116667)              # 350000/3 rounded
            self.assertEqual(week["new_customers"], 2)         # c1, c2

            prev_week = payload["kpis"]["week"]["previous"]
            self.assertEqual(prev_week["orders"], 1)           # o5
            self.assertEqual(prev_week["gross"], 400000)
            self.assertEqual(prev_week["new_customers"], 1)    # c3

            changes = payload["kpis"]["week"]["changes"]
            self.assertEqual(changes["orders"], 300.0)
            self.assertEqual(changes["gross"], -12.5)
            self.assertEqual(changes["new_customers"], 100.0)

    def test_percentage_change_is_none_without_previous(self):
        with frozen_clock(FROZEN):
            payload = build_payload(14)  # empty database
            self.assertIsNone(payload["kpis"]["week"]["changes"]["orders"])
            self.assertEqual(payload["kpis"]["today"]["current"]["orders"], 0)
            self.assertEqual(payload["kpis"]["today"]["current"]["gross"], 0)
            self.assertEqual(payload["kpis"]["today"]["current"]["aov"], 0)

    def test_tehran_midnight_boundary(self):
        """UTC 20:29 belongs to the previous Tehran day, UTC 20:30 to the
        new one -- the KPI windows must cut exactly there."""
        with frozen_clock(FROZEN):
            from apps.orders.models import Order

            before = make_order(total=1000, subtotal=1000)
            _set_created(before, utc(2026, 10, 9, 20, 29))
            after = make_order(total=2000, subtotal=2000)
            _set_created(after, utc(2026, 10, 9, 20, 30))

            today = build_payload(14)["kpis"]["today"]["current"]
            self.assertEqual(today["orders"], 1)
            self.assertEqual(today["gross"], 2000)
            week = build_payload(14)["kpis"]["week"]["current"]
            self.assertEqual(week["orders"], 2)

    def test_chart_shape_and_geometry(self):
        with frozen_clock(FROZEN):
            self._fixture_orders()
            payload = build_payload(14)
            chart = payload["chart"]
            self.assertEqual(len(chart), 14)
            self.assertEqual(chart[-1]["date"], dt.date(2026, 10, 10))
            self.assertEqual(chart[0]["date"], dt.date(2026, 9, 27))
            # gross per day: today 300000 (o1+o2), yesterday 50000 (o3),
            # 8 days ago 400000 (o5)
            self.assertEqual(chart[-1]["gross"], 300000)
            self.assertEqual(chart[-2]["gross"], 50000)
            self.assertEqual(payload["chart_max"], 400000)
            self.assertEqual(payload["chart_width"], 14 * 36)
            for i, point in enumerate(chart):
                self.assertEqual(point["x"], i * 36 + 6)
                self.assertEqual(point["bar_y"], 140 - point["bar_h"])
                self.assertLessEqual(point["bar_h"], 120)
                if point["gross"]:
                    self.assertGreaterEqual(point["bar_h"], 2)
            # Jalali labels for the last point: ۱۴۰۵/۰۷/۱۸
            self.assertEqual(chart[-1]["jlabel"], "۰۷/۱۸")
            self.assertEqual(chart[-1]["jfull"], "۱۴۰۵/۰۷/۱۸")

    def test_top_products_exclude_cancelled_and_unpaid(self):
        with frozen_clock(FROZEN):
            self._fixture_orders()
            top = build_payload(14)["top_products"]
            by_name = {row["name"]: row["qty"] for row in top}
            # product_a: o1 qty2 + o3 qty1 = 3 (o4 unpaid -> excluded)
            self.assertEqual(by_name["قاشق چوبی"], 3)
            # product_b: only o5 (paid, open). o2 is CANCELLED -> excluded
            self.assertEqual(by_name.get("کتری لعابی", 0), 1)
            self.assertEqual(top[0]["name"], "قاشق چوبی")
            self.assertTrue(top[0]["url"].endswith(
                f"/admin/products/product/{self.product_a.pk}/change/"
            ))

    def test_latest_orders_and_logs(self):
        with frozen_clock(FROZEN):
            orders = self._fixture_orders()
            LogEntry.objects.log_action(
                user_id=self.admin.pk,
                content_type_id=None, object_id=str(orders[0].pk),
                object_repr=orders[0].order_number, action_flag=ADDITION,
            )
            payload = build_payload(14)
            self.assertEqual(len(payload["latest_orders"]), 6)
            # newest first: o1 (10-10 05:30) vs o2 (06:30) -> o2 first
            self.assertEqual(payload["latest_orders"][0]["id"], orders[1].pk)
            self.assertTrue(payload["latest_orders"][0]["url"].endswith(
                f"/admin/orders/order/{orders[1].pk}/change/"
            ))
            logs = payload["latest_logs"]
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["action_label"], "افزودن")

    def test_payload_is_pickle_safe_for_cache(self):
        with frozen_clock(FROZEN):
            payload = build_payload(14)
            restored = pickle.loads(pickle.dumps(payload))
            self.assertEqual(restored["kpis"], payload["kpis"])
            self.assertEqual(restored["chart"][0]["date"], payload["chart"][0]["date"])

    def test_days_30_switch(self):
        with frozen_clock(FROZEN):
            payload = build_payload(30)
            self.assertEqual(payload["chart_days"], 30)
            self.assertEqual(len(payload["chart"]), 30)
            self.assertEqual(payload["chart_width"], 30 * 36)
        # days other than 30 collapse to 14
        with frozen_clock(FROZEN):
            self.assertEqual(build_payload(7)["chart_days"], 14)


@override_settings(**PLAIN_STATIC)
class DashboardCachingTests(CacheIsolationMixin, TestCase):
    def test_second_call_hits_cache_with_zero_queries(self):
        make_superuser(username="cacheowner", phone="+989000004444")
        with frozen_clock(FROZEN):
            first = get_dashboard(14)
            with CaptureQueriesContext(connection) as ctx:
                second = get_dashboard(14)
            self.assertEqual(len(ctx.captured_queries), 0)
            self.assertEqual(second["generated_at"], first["generated_at"])

    def test_cold_build_is_bounded(self):
        """No N+1: the whole payload costs a fixed, small number of
        queries no matter how many rows exist."""
        make_superuser(username="boundowner", phone="+989000005555")
        for i in range(12):
            make_order(total=1000 + i, subtotal=1000 + i)
        with frozen_clock(FROZEN):
            with CaptureQueriesContext(connection) as ctx:
                build_payload(14)
            self.assertLessEqual(len(ctx.captured_queries), 25)
            self.assertGreater(len(ctx.captured_queries), 5)

    def test_days_keys_are_separate(self):
        with frozen_clock(FROZEN):
            get_dashboard(14)
            get_dashboard(30)
            from django.core.cache import cache

            self.assertIsNotNone(cache.get(CACHE_KEY.format(days=14)))
            self.assertIsNotNone(cache.get(CACHE_KEY.format(days=30)))


@override_settings(**PLAIN_STATIC)
class DashboardViewTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.url = reverse("admin:index")

    def test_index_carries_payload_and_persian_numbers(self):
        admin = make_superuser(username="viewowner", phone="+989000006666")
        self.client.force_login(admin)
        product = make_product(price=100000)
        order = make_order(product=product, total=350000, subtotal=350000)
        with frozen_clock(FROZEN):
            type(order).objects.filter(pk=order.pk).update(created_at=utc(2026, 10, 10, 5, 30))
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        payload = response.context["cusin_dashboard"]
        self.assertEqual(payload["kpis"]["today"]["current"]["gross"], 350000)
        html = response.content.decode()
        # Persian digits + «تومان» (numfa/toman filters)
        self.assertIn("۳۵۰٬۰۰۰", html)
        self.assertIn("تومان", html)
        # tooltip with the exact gross definition (B1 requirement)
        self.assertIn("وضعیت پرداختشان «پرداخت شده» است", html)
        # accessible chart table next to the SVG
        self.assertIn("cusin-chart-table", html)
        self.assertIn("cusin-readiness", html)  # superuser-only card shown

    def test_days_30_via_query_string(self):
        admin = make_superuser(username="daysowner", phone="+989000007777")
        self.client.force_login(admin)
        with frozen_clock(FROZEN):
            response = self.client.get(self.url, {"days": "30"})
        self.assertEqual(response.context["cusin_dashboard_days"], 30)
        self.assertEqual(len(response.context["cusin_dashboard"]["chart"]), 30)

    def test_empty_state(self):
        admin = make_superuser(username="emptyowner", phone="+989000008888")
        self.client.force_login(admin)
        with frozen_clock(FROZEN):
            response = self.client.get(self.url)
        self.assertContains(response, "هنوز سفارشی ثبت نشده است.")

    def test_readiness_card_is_superuser_only(self):
        staff = make_staff(permissions=["orders.view_order"],
                           username="+989000009999", phone="+989000009999")
        self.client.force_login(staff)
        with frozen_clock(FROZEN):
            response = self.client.get(self.url)
        self.assertEqual(response.context["cusin_readiness"], [])
        self.assertNotIn("آمادگی راه‌اندازی", response.content.decode())

    def test_action_cards_gated_by_permission(self):
        staff = make_staff(permissions=["orders.view_order"],
                           username="+989000010000", phone="+989000010000")
        self.client.force_login(staff)
        with frozen_clock(FROZEN):
            response = self.client.get(self.url)
        ids = {card["id"] for card in response.context["cusin_actions"]}
        self.assertEqual(
            ids,
            {"paid_to_process", "awaiting_payment", "needs_refund", "pickup_waiting"},
        )
        html = response.content.decode()
        self.assertIn("پرداخت‌شده در انتظار پردازش", html)
        self.assertNotIn("موجودی کم", html)          # products card hidden
        self.assertNotIn("cusin-readiness", html)

    def test_products_only_staff_sees_product_cards(self):
        staff = make_staff(permissions=["products.view_product"],
                           username="+989000011111", phone="+989000011111")
        self.client.force_login(staff)
        with frozen_clock(FROZEN):
            response = self.client.get(self.url)
        ids = {card["id"] for card in response.context["cusin_actions"]}
        self.assertEqual(ids, {"low_stock", "out_of_stock", "no_image"})
        self.assertEqual(response.context["cusin_perms"]["orders"], False)

    def test_all_action_card_urls_open_working_changelists(self):
        admin = make_superuser(username="cardsowner", phone="+989000012222")
        self.client.force_login(admin)
        make_order()
        make_product(stock_quantity=0)
        with frozen_clock(FROZEN):
            payload = build_payload(14)
            for card in payload["actions"]:
                with self.subTest(card=card["id"]):
                    response = self.client.get(card["url"])
                    self.assertEqual(
                        response.status_code, 200,
                        f"card {card['id']} URL {card['url']} is broken",
                    )

    def test_action_card_counts_match_filters(self):
        """The number on a card equals the row count of the list it links
        to -- the owner must never see a count that the page contradicts."""
        admin = make_superuser(username="countsowner", phone="+989000013333")
        self.client.force_login(admin)
        from apps.orders.models import Order

        make_order(payment_status=Order.PaymentStatus.PAID,
                   status=Order.Status.CONFIRMED)          # paid_to_process
        make_order(payment_status=Order.PaymentStatus.UNPAID,
                   status=Order.Status.PENDING)            # awaiting_payment
        make_order(payment_status=Order.PaymentStatus.PAID,
                   status=Order.Status.CANCELLED,
                   refund_status=Order.RefundStatus.REQUIRED)  # needs_refund
        make_product(stock_quantity=2)                     # low_stock (<=5?)
        make_product(stock_quantity=0)                     # out_of_stock
        make_product(stock_quantity=50)                    # nothing

        with frozen_clock(FROZEN):
            payload = build_payload(14)
            by_id = {card["id"]: card for card in payload["actions"]}
            self.assertEqual(by_id["paid_to_process"]["count"], 1)
            self.assertEqual(by_id["awaiting_payment"]["count"], 1)
            self.assertEqual(by_id["needs_refund"]["count"], 1)
            self.assertEqual(by_id["out_of_stock"]["count"], 1)
            # changelists return the same counts
            for card_id in ("paid_to_process", "awaiting_payment", "needs_refund"):
                response = self.client.get(by_id[card_id]["url"])
                self.assertEqual(response.context["cl"].result_count, 1,
                                 f"{card_id} list disagrees with card count")
            # low-stock card links to ?low_stock=3 (at/below threshold,
            # NOT zero) so list count == card count exactly; the legacy
            # ?low_stock=1 (which includes zero) keeps its old behaviour.
            self.assertIn("low_stock=3", by_id["low_stock"]["url"])
            response = self.client.get(by_id["low_stock"]["url"])
            self.assertEqual(response.context["cl"].result_count, 1)
            legacy = self.client.get(
                reverse("admin:products_product_changelist"), {"low_stock": "1"}
            )
            self.assertEqual(legacy.context["cl"].result_count, 2)
            response = self.client.get(by_id["out_of_stock"]["url"])
            self.assertEqual(response.context["cl"].result_count, 1)
            response = self.client.get(by_id["no_image"]["url"])
            self.assertEqual(response.context["cl"].result_count,
                             by_id["no_image"]["count"])


@override_settings(**PLAIN_STATIC)
class ReadinessTests(CacheIsolationMixin, TestCase):
    def test_readiness_reuses_production_checks(self):
        admin = make_superuser(username="readyowner", phone="+989000014444")
        self.client.force_login(admin)
        with frozen_clock(FROZEN):
            response = self.client.get(reverse("admin:index"))
        readiness = response.context["cusin_readiness"]
        ids = [item["id"] for item in readiness]
        self.assertEqual(
            ids,
            ["gateway", "sms", "two_factor", "site_profile", "https", "debug", "admin_url"],
        )
        by_id = {item["id"]: item for item in readiness}
        # test settings keep the mock gateway -> card must flag it
        self.assertFalse(by_id["gateway"]["ok"])
        self.assertIn("mock", by_id["gateway"]["detail"])
        # DEBUG is off under the test runner
        self.assertTrue(by_id["debug"]["ok"])

    def test_readiness_reflects_settings_changes(self):
        with override_settings(PAYMENT_GATEWAY="zarinpal",
                               PAYMENT_ZARINPAL_SANDBOX=False,
                               ADMIN_2FA_REQUIRED=True):
            from apps.adminui.dashboard import readiness_checks

            by_id = {item["id"]: item for item in readiness_checks()}
            self.assertTrue(by_id["gateway"]["ok"])
            self.assertTrue(by_id["two_factor"]["ok"])


@override_settings(**PLAIN_STATIC)
class DashboardPermissionAccessTests(CacheIsolationMixin, TestCase):
    """Cards hidden is only half of B1: the underlying data must not leak
    through the index for users without view permissions."""

    def test_no_orders_permission_no_order_numbers_in_html(self):
        staff = make_staff(permissions=["products.view_product"],
                           username="+989000015555", phone="+989000015555")
        self.client.force_login(staff)
        order = make_order()
        with frozen_clock(FROZEN):
            response = self.client.get(reverse("admin:index"))
        html = response.content.decode()
        self.assertNotIn(order.order_number, html)
        self.assertNotIn(reverse("admin:orders_order_change", args=[order.pk]), html)

    def test_customer_without_staff_gets_redirect(self):
        customer = make_customer()
        self.client.force_login(customer)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
