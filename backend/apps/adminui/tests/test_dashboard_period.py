"""
Item 9 -- the dashboard: period switcher, chart ticks, tooltips, and no
app/model list at the bottom.

Before: two periods only (۱۴/۳۰ روز, and anything else silently collapsed
back to ۱۴), a chart that labelled EVERY bar (30 Jalali labels overlapping
into a smear), KPIs that ignored the switcher entirely, and a full Django
app/model index bolted onto the bottom of a page that already had a
sidebar with the same links.
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.testing import CacheIsolationMixin, frozen_clock
from apps.orders.models import Order

from ..dashboard import (
    MAX_CHART_TICKS,
    PERIODS,
    PERIOD_LABELS,
    build_payload,
    normalize_days,
    period_cookie_name,
)
from .helpers import PLAIN_STATIC, make_order, make_superuser

FROZEN = __import__("datetime").datetime(
    2026, 10, 10, 12, 0,
    tzinfo=__import__("datetime").timezone(
        __import__("datetime").timedelta(hours=3, minutes=30)),
)


class PeriodChoiceTests(CacheIsolationMixin, TestCase):
    def test_all_five_periods_are_supported(self):
        self.assertEqual(PERIODS, (1, 7, 14, 30, 90))

    def test_labels_are_persian_and_cover_every_period(self):
        self.assertEqual(
            [PERIOD_LABELS[d] for d in PERIODS],
            ["امروز", "۷ روز", "۱۴ روز", "۳۰ روز", "۹۰ روز"],
        )

    def test_normalize_days_accepts_only_real_periods(self):
        for value in ("1", 1, "7", 7, "14", 14, "30", 30, "90", 90):
            with self.subTest(value=value):
                self.assertEqual(normalize_days(value), int(value))
        for bogus in (None, "", "0", "2", "365", "bogus", "-7", [30]):
            with self.subTest(value=bogus):
                self.assertEqual(normalize_days(bogus), 14)


class ChartShapeTests(CacheIsolationMixin, TestCase):
    def test_daily_period_has_one_bar_per_day(self):
        with frozen_clock(FROZEN):
            for days in (7, 14, 30, 90):
                with self.subTest(days=days):
                    self.assertEqual(len(build_payload(days)["chart"]), days)

    def test_today_is_hourly_not_one_lonely_bar(self):
        """«امروز» used to be a single bar labelled ۱۰/۱۸ -- useless for a
        day the owner is living through. Now 24 hourly buckets."""
        with frozen_clock(FROZEN):
            payload = build_payload(1)
        self.assertTrue(payload["chart_hourly"])
        self.assertEqual(len(payload["chart"]), 24)
        self.assertEqual([p["hour"] for p in payload["chart"]], list(range(24)))
        self.assertEqual(payload["chart"][9]["jlabel"], "۰۹:۰۰")

    def test_at_most_seven_axis_ticks_and_they_are_evenly_spread(self):
        """30 bars each labelled «۲۳ مهر» overlapped into a smear."""
        with frozen_clock(FROZEN):
            for days in (7, 14, 30, 90):
                with self.subTest(days=days):
                    ticks = build_payload(days)["chart_ticks"]
                    self.assertLessEqual(len(ticks), MAX_CHART_TICKS)
                    self.assertGreaterEqual(len(ticks), 2)
                    # First and last are always shown, so the range is clear.
                    self.assertEqual(ticks[0]["index"], 0)
                    self.assertEqual(ticks[-1]["index"], days - 1)
                    gaps = [b["index"] - a["index"]
                            for a, b in zip(ticks, ticks[1:])]
                    if len(gaps) > 1:
                        self.assertLessEqual(max(gaps) - min(gaps), 1)

    def test_short_periods_label_every_bar(self):
        """No point thinning 7 labels -- there is room for all of them."""
        with frozen_clock(FROZEN):
            ticks = build_payload(7)["chart_ticks"]
        self.assertEqual(len(ticks), 7)

    def test_axis_label_is_day_and_persian_month(self):
        with frozen_clock(FROZEN):
            ticks = build_payload(30)["chart_ticks"]
        for tick in ticks:
            with self.subTest(label=tick["label"]):
                # «۲۳ مهر» -- Persian digits, Persian month name.
                self.assertRegex(tick["label"], r"^[۰-۹]+ (فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)$")

    def test_every_bar_carries_tooltip_data(self):
        with frozen_clock(FROZEN):
            payload = build_payload(14)
        for point in payload["chart"]:
            with self.subTest(date=point["jfull"]):
                self.assertTrue(point["jfull"])
                self.assertTrue(point["gross_toman"].endswith("تومان"))
                self.assertIn("orders", point)

    def test_bars_have_positive_width(self):
        with frozen_clock(FROZEN):
            for days in (1, 90):
                with self.subTest(days=days):
                    for point in build_payload(days)["chart"]:
                        self.assertGreaterEqual(point["bar_w"], 6)

    def test_hourly_buckets_actually_count_orders(self):
        with frozen_clock(FROZEN):
            _paid_order(total=1000)
            payload = build_payload(1)
        # FROZEN is 12:00 Tehran -> the 12:00 bucket holds the sale.
        self.assertEqual(payload["chart"][12]["gross"], 1000)
        self.assertEqual(sum(p["gross"] for p in payload["chart"]), 1000)


class PeriodDrivesTheNumbersTests(CacheIsolationMixin, TestCase):
    """The switcher must move the KPIs and the best-sellers, not just the
    chart -- that was the whole point of the control."""

    def test_kpi_card_follows_the_period(self):
        with frozen_clock(FROZEN):
            seven = build_payload(7)
            ninety = build_payload(90)
        self.assertEqual(seven["kpi_list"][1]["title"], "۷ روز")
        self.assertEqual(ninety["kpi_list"][1]["title"], "۹۰ روز")
        self.assertEqual(seven["period_label"], "۷ روز")
        self.assertEqual(ninety["period_label"], "۹۰ روز")

    def test_today_card_is_always_there(self):
        with frozen_clock(FROZEN):
            for days in PERIODS:
                with self.subTest(days=days):
                    self.assertEqual(build_payload(days)["kpi_list"][0]["title"], "امروز")

    def test_best_sellers_window_follows_the_period(self):
        with frozen_clock(FROZEN):
            payload = build_payload(7)
        self.assertEqual(payload["period_label"], "۷ روز")
        # _top_products() is called with the selected window; an order from
        # 40 days ago must therefore not appear in the 7-day list.
        self.assertIsInstance(payload["top_products"], list)


@override_settings(**PLAIN_STATIC)
class PeriodPersistenceTests(CacheIsolationMixin, TestCase):
    """Remembered per user: two owners on one browser don't fight."""

    def setUp(self):
        self.owner = make_superuser(username="dash-owner", phone="+989000030001")
        self.other = make_superuser(username="dash-owner-2", phone="+989000030002")
        self.client.force_login(self.owner)
        self.url = reverse("admin:index")

    def test_cookie_name_is_per_user(self):
        self.assertNotEqual(period_cookie_name(self.owner),
                            period_cookie_name(self.other))
        self.assertTrue(period_cookie_name(self.owner).startswith("cusin_dash_days_"))

    def test_query_param_wins_over_the_remembered_period(self):
        self.client.get(self.url, {"days": "30"})
        response = self.client.get(self.url, {"days": "7"})
        self.assertEqual(response.context["cusin_dashboard_days"], 7)

    def test_query_param_overrides_a_cookie_too(self):
        self.client.cookies[period_cookie_name(self.owner)] = "30"
        response = self.client.get(self.url, {"days": "7"})
        self.assertEqual(response.context["cusin_dashboard_days"], 7)

    def test_the_period_is_remembered_without_the_query_param(self):
        """The bug: choosing ۳۰ روز and coming back to /admin/ fell back
        to the default, because the choice lived in a client-side cookie
        only."""
        self.client.get(self.url, {"days": "30"})
        response = self.client.get(self.url)
        self.assertEqual(response.context["cusin_dashboard_days"], 30)

    def test_the_period_survives_a_trip_through_another_admin_page(self):
        self.client.get(self.url, {"days": "30"})
        # a page that is NOT the dashboard must not reset it
        self.client.get(reverse("admin:products_product_changelist"))
        self.client.get(reverse("admin:orders_order_changelist"))
        response = self.client.get(self.url)
        self.assertEqual(response.context["cusin_dashboard_days"], 30)

    def test_the_last_choice_replaces_the_previous_one(self):
        self.client.get(self.url, {"days": "90"})
        self.client.get(self.url, {"days": "7"})
        response = self.client.get(self.url)
        self.assertEqual(response.context["cusin_dashboard_days"], 7)

    def test_each_owner_keeps_their_own_period(self):
        """A shared shop computer must not mix the two owners up."""
        self.client.get(self.url, {"days": "30"})
        other = self.client_class()
        other.force_login(self.other)
        other.get(self.url, {"days": "90"})

        self.assertEqual(
            self.client.get(self.url).context["cusin_dashboard_days"], 30
        )
        self.assertEqual(
            other.get(self.url).context["cusin_dashboard_days"], 90
        )

    def test_an_owner_who_chose_nothing_gets_the_default(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["cusin_dashboard_days"], 14)

    def test_a_bogus_stored_period_falls_back_to_the_default(self):
        session = self.client.session
        session["cusin_dash_days"] = "not-a-number"
        session.save()
        self.assertEqual(
            self.client.get(self.url).context["cusin_dashboard_days"], 14
        )

    def test_a_legacy_cookie_is_still_honoured(self):
        """An owner mid-session with the old cookie keeps their range."""
        self.client.cookies[period_cookie_name(self.owner)] = "30"
        response = self.client.get(self.url)
        self.assertEqual(response.context["cusin_dashboard_days"], 30)

    def test_someone_elses_cookie_does_not_apply(self):
        self.client.cookies[period_cookie_name(self.other)] = "90"
        response = self.client.get(self.url)
        self.assertEqual(response.context["cusin_dashboard_days"], 14)

    def test_a_bogus_cookie_falls_back_to_the_default(self):
        self.client.cookies[period_cookie_name(self.owner)] = "not-a-number"
        response = self.client.get(self.url)
        self.assertEqual(response.context["cusin_dashboard_days"], 14)

    def test_the_switcher_works_without_javascript(self):
        """Nothing on the page depends on a script to change the period."""
        html = self.client.get(self.url).content.decode()
        for days in (1, 7, 14, 30, 90):
            with self.subTest(days=days):
                self.assertIn(f'href="?days={days}"', html)

    def test_all_five_chips_are_rendered_with_the_right_one_active(self):
        html = self.client.get(self.url, {"days": "90"}).content.decode()
        for days in (1, 7, 14, 30, 90):
            with self.subTest(days=days):
                self.assertIn(f'data-cusin-period="{days}"', html)
        self.assertRegex(
            html,
            r'<a href="\?days=90"[^>]*data-cusin-period="90"[^>]*class="cusin-chip is-active"',
        )
        # ...and exactly one chip is active.
        self.assertEqual(html.count("cusin-chip is-active"), 1)

    def test_chips_carry_their_persian_labels(self):
        html = self.client.get(self.url).content.decode()
        for label in ("امروز", "۷ روز", "۱۴ روز", "۳۰ روز", "۹۰ روز"):
            with self.subTest(label=label):
                self.assertIn(f">{label}</a>", html)


def _paid_order(total=250000):
    """A paid order today, so the chart has something to draw."""
    order = make_order(total=total, subtotal=total)
    Order.objects.filter(pk=order.pk).update(payment_status=Order.PaymentStatus.PAID)
    return order


@override_settings(**PLAIN_STATIC)
class DashboardChromeTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.owner = make_superuser(username="dash-chrome", phone="+989000030003")
        self.client.force_login(self.owner)

    def _page(self, **params):
        with frozen_clock(FROZEN):
            _paid_order()
            response = self.client.get(reverse("admin:index"), params)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_app_model_list_is_gone(self):
        """It duplicated the sidebar and pushed the real content down."""
        html = self._page()
        self.assertNotIn("cusin-appsections", html)
        self.assertNotIn("بخش‌های مدیریت", html)
        # The non-themed fallback branch is untouched.
        self.assertNotIn('id="content-main"', html.split("cusin-dash", 1)[0].join([""]))

    def test_chart_renders_ticks_and_tooltip_hooks(self):
        html = self._page()
        self.assertIn("data-cusin-chart", html)
        self.assertIn("data-cusin-chart-tip", html)
        self.assertIn("cusin-chart-tick", html)
        self.assertIn("data-amount=", html)

    def test_chart_titles_do_not_claim_a_day_count_for_today(self):
        today = self._page(days="1")
        self.assertIn("فروش ساعتیِ امروز", today)
        self.assertNotIn("فروش در امروز اخیر", today)
        week = self._page(days="7")
        self.assertIn("فروش در ۷ روز اخیر", week)

    def test_best_seller_title_follows_the_period(self):
        self.assertIn("پرفروش‌های ۷ روز اخیر", self._page(days="7"))
        self.assertIn("پرفروش‌های امروز اخیر", self._page(days="1"))

    @staticmethod
    def kpi_header_block(html):
        return html[
            html.index("cusin-kpis-head"): html.index(
                'class="cusin-kpis"', html.index("cusin-kpis-head")
            )
        ]

    def test_the_switcher_sits_next_to_the_kpis_not_in_the_page_header(self):
        """At 1366px the chips were a full row away from the numbers they
        change, over on the far side of a right-to-left page."""
        html = self._page()
        self.assertIn("cusin-kpis-head", html)
        self.assertIn("cusin-kpis-block", html)
        header = html[
            html.index("cusin-dash-head"): html.index("cusin-kpis-block")
        ]
        self.assertNotIn("cusin-days-toggle", header)
        block = self.kpi_header_block(html)
        self.assertIn("cusin-days-toggle", block)
        self.assertIn("شاخص‌های کلیدی", block)

    def test_every_period_chip_is_in_the_kpi_header(self):
        block = self.kpi_header_block(self._page())
        for days in (1, 7, 14, 30, 90):
            with self.subTest(days=days):
                self.assertIn(f'href="?days={days}"', block)

    def test_both_kpi_cards_are_rendered(self):
        """«امروز» and the chosen range: two cards, one row."""
        html = self._page(days="30")
        self.assertEqual(html.count("cusin-kpi-card"), 2)
        self.assertIn("امروز", html)
        self.assertIn("۳۰ روز", html)


class DashboardCssJsContractTests(TestCase):
    def setUp(self):
        base = Path(settings.BASE_DIR)
        self.js = (base / "static/admin_theme/js/theme.js").read_text(encoding="utf-8")
        self.css = (base / "static/admin_theme/css/theme.css").read_text(encoding="utf-8")

    def test_card_titles_may_wrap_to_two_lines(self):
        block = self.css.split(".cusin-card-head h2 {", 1)[1].split("}", 1)[0]
        self.assertIn("-webkit-line-clamp: 2", block)
        self.assertIn("overflow: hidden", block)

    def test_secondary_card_text_is_one_step_smaller(self):
        block = self.css.split(".cusin-card-note {", 1)[1].split("}", 1)[0]
        self.assertIn("font-size: 0.6875rem", block)

    def test_the_kpi_row_uses_the_whole_content_width(self):
        """A fixed 3-column track left a third of the row empty, which in
        RTL read as the KPIs crowding the right half."""
        block = self.css.split(".cusin-kpis {", 1)[1].split("}", 1)[0]
        self.assertIn("auto-fit", block)
        self.assertNotIn("repeat(3", block)

    def test_the_kpi_heading_and_the_switcher_share_one_row(self):
        block = self.css.split(".cusin-kpis-head {", 1)[1].split("}", 1)[0]
        self.assertIn("display: flex", block)
        self.assertIn("justify-content: space-between", block)
        self.assertIn("flex-wrap: wrap", block)

    def test_the_period_switcher_needs_no_cookie_and_no_script(self):
        """Server-side memory: no cookie to block, nothing to re-run."""
        self.assertNotIn("cusin_dash_days", self.js)
        self.assertNotIn("document.cookie", self.js)
        template = (
            Path(settings.BASE_DIR) / "templates" / "admin" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn('href="?days={{ period.days }}"', template)

    def test_tooltip_works_on_touch_not_only_hover(self):
        self.assertIn('addEventListener("touchstart"', self.js)
        self.assertIn('addEventListener("click"', self.js)
        self.assertIn('addEventListener("mouseover"', self.js)

    def test_js_balances(self):
        self.assertEqual(self.js.count("{"), self.js.count("}"))
